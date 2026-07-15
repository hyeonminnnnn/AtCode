# Phase 1 세 역할 Runtime과 안내형 설치 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 1을 PM·Developer·Reviewer 세 역할로 전환하고, WSL 사용자가 한 명령으로 환경 점검부터 launcher 설치와 doctor까지 완료하게 한다.

**Architecture:** `Role` Enum을 활성 역할의 단일 기준으로 사용한다. ConfigurationService와 JsonStateStore 입력 경계에서 schema version 1의 `tester`·`docs`만 정규화하고, SessionService는 실제 Window 집합이 세 역할과 정확히 같을 때만 정상으로 판정한다. 설치 UX는 기존 `scripts/install.sh`의 작은 Bash 함수로 구성하며 Runtime Port·Adapter·Backend에는 설치 책임을 넣지 않는다.

**Tech Stack:** Python 3.11+, pytest, Bash, tmux, Codex CLI, JSON schema version 1

## Global Constraints

- Runtime 데이터는 `ATCODE_HOME`에서만 읽고 쓰며 대상 프로젝트에 AtCode 파일을 만들지 않는다.
- Phase 1 역할은 `pm`, `developer`, `reviewer`로 고정한다.
- `tester`, `docs` 외의 알 수 없는 legacy 역할은 오류로 처리한다.
- Phase 1에는 `/next`, `send-keys`, `capture-pane`, Task Queue를 구현하지 않는다.
- 일반 설치에는 Python 가상환경, pip, pytest를 요구하지 않는다.
- `sudo`, 원격 Codex 설치, `.bashrc` 수정, 로그인은 실행 전 사용자 동의를 받는다.
- 사용자 입력을 명령·URL·패키지 이름으로 전달하지 않는다.
- 새 외부 의존성을 추가하지 않고 `.env`, `.env.local`을 읽거나 수정하지 않는다.

---

### Task 1: Role Domain과 설정 자동 전환

**Files:**
- Modify: `src/atcode/domain/models.py`
- Modify: `src/atcode/application/configuration.py`
- Modify: `tests/unit/test_configuration.py`
- Modify: `tests/integration/test_cli.py`

**Interfaces:**
- Produces: `Role = {PM, DEVELOPER, REVIEWER}`
- Produces: `ConfigurationService.effective(project) -> RuntimeConfig`가 세 역할만 반환
- Produces: `set/unset`이 저장 전 legacy 역할을 제거

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_configuration.py`에 정확한 역할 집합, legacy 설정 읽기, 읽기 시 원본 불변, 다음 설정 저장 시 legacy key 제거, unknown 역할 거부를 추가한다.

```python
def test_phase_one_has_exactly_three_roles() -> None:
    assert tuple(role.value for role in Role) == ("pm", "developer", "reviewer")


def test_legacy_roles_are_ignored_without_mutating_file(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    stored = {
        "schemaVersion": 1,
        "roles": {
            "reviewer": {"adapter": "gemini"},
            "tester": {"adapter": "codex"},
            "docs": {"adapter": "claude"},
        },
    }
    store.write_project(project, stored)
    config = service.effective(project)
    assert set(config.roles) == {Role.PM, Role.DEVELOPER, Role.REVIEWER}
    assert store.read_project(project) == stored


def test_next_config_write_removes_legacy_roles(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_project(project, {
        "schemaVersion": 1,
        "roles": {
            "tester": {"adapter": "codex"},
            "docs": {"adapter": "codex"},
        },
    })
    service.set(project, "roles.reviewer.adapter", "gemini", global_scope=False)
    assert store.read_project(project) == {
        "schemaVersion": 1,
        "roles": {"reviewer": {"adapter": "gemini"}},
    }
```

CLI `config show`에는 `pm`, `developer`, `reviewer`가 있고 `tester`, `docs`가 없다고 assertion한다.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest -q tests/unit/test_configuration.py tests/integration/test_cli.py`

Expected: 5역할 Enum과 legacy 출력 때문에 FAIL.

- [ ] **Step 3: 최소 구현**

`Role.TESTER`, `Role.DOCS`와 `_DEFAULT`의 두 항목을 제거한다. 설정 layer는 원본을 바꾸지 않고 다음 함수로 정규화한다.

```python
_LEGACY_ROLES = frozenset({"tester", "docs"})


def _normalize_legacy_roles(value: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(value)
    roles = normalized.get("roles")
    if isinstance(roles, dict):
        for role_name in _LEGACY_ROLES:
            roles.pop(role_name, None)
    return normalized
```

`effective()`는 각 layer를 정규화한 뒤 검증·병합한다. `_read_target()`도 정규화된 사본을 반환해 다음 `set/unset` 저장에서 legacy key를 제거한다. 정규화 전 legacy assignment가 정확히 `{"adapter": <allowed adapter>}`인지 확인해 malformed legacy 데이터를 허용하지 않는다.

- [ ] **Step 4: 통과 확인과 커밋**

```bash
python3 -m pytest -q tests/unit/test_configuration.py tests/integration/test_cli.py
git add src/atcode/domain/models.py src/atcode/application/configuration.py tests/unit/test_configuration.py tests/integration/test_cli.py
git commit -m "feat: reduce runtime to three roles"
```

Expected: PASS 후 커밋 성공.

---

### Task 2: legacy 상태와 tmux 세션 전환

**Files:**
- Modify: `src/atcode/infrastructure/storage/state.py`
- Modify: `src/atcode/application/sessions.py`
- Modify: `tests/unit/test_state_store.py`
- Modify: `tests/unit/test_sessions.py`
- Modify: `tests/unit/test_tmux_backend.py`

**Interfaces:**
- Consumes: Task 1의 세 역할 `Role`
- Produces: legacy 상태 읽기와 다음 저장 시 세 역할 상태
- Produces: 정확한 세 Window만 `running`

- [ ] **Step 1: 실패 테스트 작성**

`test_state_store.py`에서 5역할 schema version 1 JSON을 직접 기록한다. `read()` 결과에는 세 역할만 있지만 파일 원문은 그대로이고, `write()` 후에는 세 역할만 남는다고 검증한다.

`test_sessions.py`에 다음을 추가한다.

```python
def test_status_is_degraded_when_legacy_windows_are_extra(tmp_path: Path) -> None:
    service, backend, _state_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        ("pm", "developer", "reviewer", "tester", "docs"),
        "pm",
    )
    assert service.status().status is Lifecycle.DEGRADED
```

기존 start 테스트는 Window 이름이 `("pm", "developer", "reviewer")`인지 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest -q tests/unit/test_state_store.py tests/unit/test_sessions.py tests/unit/test_tmux_backend.py`

Expected: legacy Role 변환과 extra Window 판정에서 FAIL.

- [ ] **Step 3: 최소 구현**

`JsonStateStore.read()`는 각 item의 `role`, `adapter`, `window` 키를 먼저 읽는다. role 문자열이 `tester` 또는 `docs`이면 제외하고, 나머지는 `Role(role_name)`으로 변환해 unknown 역할을 계속 거부한다.

Session 판정은 다음으로 바꾼다.

```python
expected = {role.value for role in Role}
actual = set(snapshot.windows)
if not snapshot.exists:
    lifecycle = Lifecycle.STOPPED
elif actual == expected:
    lifecycle = Lifecycle.RUNNING
else:
    lifecycle = Lifecycle.DEGRADED
```

tmux test fixture는 세 역할만 만들고 `new-window` 호출 수를 2로 바꾼다. `send-keys`와 `capture-pane` 부재 검증은 유지한다.

- [ ] **Step 4: 통과 확인과 커밋**

```bash
python3 -m pytest -q tests/unit/test_state_store.py tests/unit/test_sessions.py tests/unit/test_tmux_backend.py
git add src/atcode/infrastructure/storage/state.py src/atcode/application/sessions.py tests/unit/test_state_store.py tests/unit/test_sessions.py tests/unit/test_tmux_backend.py
git commit -m "feat: migrate legacy role sessions"
```

Expected: PASS 후 커밋 성공.

---

### Task 3: Tester·Docs 책임을 Prompt에 병합

**Files:**
- Modify: `prompts/pm.md`
- Modify: `prompts/reviewer.md`
- Delete: `prompts/tester.md`
- Delete: `prompts/docs.md`
- Modify: `tests/unit/test_prompts.py`

**Interfaces:**
- Produces: PM의 최종 문서 정리 계약
- Produces: Reviewer의 코드 검토와 실제 테스트 계약

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_prompt_directory_has_only_active_roles() -> None:
    assert {path.stem for path in (REPO_ROOT / "prompts").glob("*.md")} == {
        "pm", "developer", "reviewer"
    }
```

PM에는 `사실`, `최종 요약`, `명령`, `경로`, `한국어`가 포함되고 Reviewer에는 `과설계`, `정상`, `오류`, `경계`, `회귀`, `미검증`, `실행 명령`, `실제 출력`이 포함된다고 검증한다.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest -q tests/unit/test_prompts.py`

Expected: 병합 책임 누락과 두 파일 존재로 FAIL.

- [ ] **Step 3: Prompt 병합과 승인된 파일 삭제**

`pm.md`에 실제 구현·검증과 명령·경로·설정 키를 대조하는 최종 요약, 의미를 보존하는 한국어 윤문 절차를 추가한다. 프로젝트 문서 수정은 명세에 있을 때 Developer 작업으로 배정한다.

`reviewer.md`에 완료 조건별 정상·오류·경계·회귀 시나리오, 좁은 테스트부터 전체 회귀까지의 실행 순서, 실패 명령·환경·실제 출력, 미검증 분류와 출시 판단 근거를 추가한다.

```bash
git rm prompts/tester.md prompts/docs.md
```

- [ ] **Step 4: 통과 확인과 커밋**

```bash
python3 -m pytest -q tests/unit/test_prompts.py
git add prompts/pm.md prompts/reviewer.md tests/unit/test_prompts.py
git commit -m "feat: merge tester and docs responsibilities"
```

Expected: PASS 후 커밋 성공.

---

### Task 4: doctor의 실행 가능한 hint 출력

**Files:**
- Modify: `src/atcode/cli.py`
- Modify: `tests/integration/test_cli.py`

**Interfaces:**
- Produces: 각 `DiagnosticResult.hint`를 해당 doctor 결과 바로 아래에 출력

- [ ] **Step 1: 실패 테스트 작성**

Unavailable FakeAdapter에 `hint="WSL용 Codex를 설치하세요."`를 넣고 기존 doctor 테스트에 다음 assertion을 추가한다.

```python
assert "WSL용 Codex를 설치하세요." in stdout
```

- [ ] **Step 2: 실패 확인과 최소 구현**

Run: `python3 -m pytest -q tests/integration/test_cli.py::test_doctor_reports_missing_adapter_without_traceback`

Expected: hint 미출력으로 FAIL.

doctor 결과 loop에 추가한다.

```python
if result.hint:
    print(f"      Hint: {result.hint}", file=stdout)
```

- [ ] **Step 3: 통과 확인과 커밋**

```bash
python3 -m pytest -q tests/integration/test_cli.py
git add src/atcode/cli.py tests/integration/test_cli.py
git commit -m "feat: show doctor recovery hints"
```

Expected: PASS 후 커밋 성공.

---

### Task 5: 비개발자용 안내형 WSL 설치기

**Files:**
- Modify: `scripts/install.sh`
- Modify: `tests/integration/test_install_scripts.py`

**Interfaces:**
- Produces: `bash scripts/install.sh` 안내형 설치
- Produces: `bash scripts/install.sh --launcher-only` launcher 전용 설치

- [ ] **Step 1: 실패 테스트 작성**

기존 install test는 `--launcher-only`를 사용한다. 추가 테스트는 알 수 없는 옵션 거부, launcher-only의 `.bashrc` 불변, Python 3.10 거부, `/mnt/c/.../codex` 거부, 실패하는 `codex --version` 거부, PATH 줄 중복 방지, non-interactive 확인의 안전한 거절을 검증한다.

Bash 함수는 제품 스크립트를 source해 호출하고, Python test가 임시 `HOME`과 가짜 executable을 제공한다. `/mnt/c/...` 판정은 `is_windows_mounted_path "/mnt/c/nvm4w/nodejs/codex"`를 직접 호출해 운영체제와 무관하게 검증한다. 실제 `sudo`, 네트워크, 로그인은 실행하지 않는다.

- [ ] **Step 2: 실패 확인**

Run: `python3 -m pytest -q tests/integration/test_install_scripts.py`

Expected: 옵션과 검사 함수가 없어 FAIL.

- [ ] **Step 3: 함수 경계 구현**

`install.sh`는 다음 고정 상수와 확인 함수를 사용한다.

```bash
CODEX_INSTALL_URL="https://chatgpt.com/codex/install.sh"
LOCAL_BIN="${HOME}/.local/bin"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

confirm() {
  local prompt="$1"
  local answer
  [[ -t 0 ]] || return 1
  read -r -p "${prompt} [y/N] " answer
  case "${answer}" in
    y|Y|yes|YES) return 0 ;;
    *) return 1 ;;
  esac
}
```

함수는 `usage`, `check_platform`, `check_python`, `ensure_tmux`, `is_windows_mounted_path`, `find_working_codex`, `ensure_codex`, `ensure_shell_path`, `ensure_codex_login`, `install_launcher`, `run_doctor`, `main`으로 제한한다.

- `check_platform`: `uname -s`가 Linux가 아니면 PowerShell의 `wsl -d Ubuntu` 안내 후 실패
- `check_python`: `python3` 존재와 3.11 이상 확인
- `ensure_tmux`: `tmux -V` 확인, Ubuntu/Debian에서만 동의 후 고정 apt 명령 실행
- `find_working_codex`: `/mnt/<drive>` 경로 거부 후 `codex --version` 실행 확인
- `ensure_codex`: curl 누락 시 Ubuntu/Debian에서 동의를 받아 고정 apt 명령으로 설치하고, 고정 URL과 작업 표시 후 동의받아 임시 파일 다운로드·실행·재검증
- `ensure_shell_path`: 현재 PATH prepend, 동의 시 `.bashrc`에 정확한 한 줄만 추가
- `ensure_codex_login`: status 확인, 동의 시 login, 실패 시 `--device-auth` 안내
- `install_launcher`: `~/.local/bin/atcode` 갱신
- `run_doctor`: 설치된 launcher로 doctor 실행
- `main`: 위 순서 조합, `--launcher-only` 분기, 다음 명령 표시

Codex 원격 설치는 고정 URL만 사용한다.

```bash
local installer
installer="$(mktemp)"
if ! curl -fsSL "${CODEX_INSTALL_URL}" -o "${installer}"; then
  rm -f -- "${installer}"
  fail "Codex 설치 스크립트를 내려받지 못했습니다."
  return 1
fi
if ! bash "${installer}"; then
  rm -f -- "${installer}"
  fail "Codex 설치가 완료되지 않았습니다."
  return 1
fi
rm -f -- "${installer}"
```

source 기반 함수 테스트를 위해 main guard를 둔다.

```bash
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
```

- [ ] **Step 4: 통과 확인과 커밋**

```bash
python3 -m pytest -q tests/integration/test_install_scripts.py
bash -n scripts/install.sh
git add scripts/install.sh tests/integration/test_install_scripts.py
git commit -m "feat: add guided wsl installer"
```

Expected: 실제 시스템 변경 없이 PASS, Bash syntax exit 0.

---

### Task 6: README와 전체 회귀 검증

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: 비개발자가 그대로 실행할 설치·전환·사용 절차

- [ ] **Step 1: README 갱신**

일반 설치는 다음만 먼저 보여준다.

```bash
cd /mnt/d/myproject/AtCode
bash scripts/install.sh
```

역할과 Workflow는 다음으로 바꾼다.

```text
PM        요구사항, 작업 배분, 결과 확인, 최종 정리
Developer 구현과 개발 단계 테스트
Reviewer  코드 리뷰, 과설계 점검, 테스트 실행과 검증

PM → Developer → Reviewer → PM
```

기존 사용자는 `atcode status`, `stop`, `start`, `attach` 순서로 3-window 전환한다고 설명한다. `/next`, pane 동시 보기, 역할 수정은 Phase 2 예정으로만 표시한다. venv·pip·pytest는 개발 검증 절에만 둔다.

- [ ] **Step 2: 전체 자동·정적 검증**

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
rg -n "Role\.(TESTER|DOCS)|roles\.(tester|docs)|prompts/(tester|docs)" src tests prompts README.md
```

Expected: 테스트 전부 PASS, 정적 검증 exit 0, 검색 결과는 legacy 호환 테스트·상수와 전환 설명뿐.

- [ ] **Step 3: README 커밋**

```bash
git add README.md
git commit -m "docs: simplify phase one onboarding"
```

- [ ] **Step 4: 실제 WSL 인수 검증**

```bash
cd /mnt/d/myproject/AtCode
bash scripts/install.sh
cd "$HOME/atcode-test/plain-project"
atcode doctor
atcode stop
atcode start
PROJECT_ID=$(atcode list | awk -F '\t' -v root="$PWD" '$3 == root {print $1}')
tmux list-windows -t "=atcode-${PROJECT_ID}" -F '#{window_name}'
```

Expected:

```text
pm
developer
reviewer
```

`doctor`는 FAIL 없이 끝나고 대상 프로젝트 파일 목록은 전후 동일해야 한다.

- [ ] **Step 5: 최종 상태 확인**

```bash
git status --short
git log --oneline -8
```

Expected: 의도하지 않은 변경이 없고 Task별 커밋이 존재.

## Phase 2 진입 조건

- 세 역할 자동 테스트와 실제 tmux Window 검증 통과
- 안내형 설치기 재실행 시 launcher와 `.bashrc` 중복 없음
- 기존 5역할 Runtime 데이터의 stop/start 전환 확인
- 대상 프로젝트에 AtCode 관리 흔적 없음
- 이후 별도 설계에서 `/next`, Reviewer 반려, Relay 저장 형식, pane layout, 사용자 정의 역할을 결정
