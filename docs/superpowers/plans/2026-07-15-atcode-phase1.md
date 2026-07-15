# AtCode Phase 1 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WSL2와 Linux에서 대상 프로젝트에 AtCode 관리 흔적을 남기지 않고, 프로젝트별 tmux AI 팀을 실행·관리하는 Python 3.11+ CLI를 구현한다.

**Architecture:** CLI → Application → Domain/Ports 방향의 계층형 모듈러 모놀리스로 구현한다. tmux, AI CLI, JSON 파일은 Infrastructure에서만 다루며 모든 Runtime 쓰기는 주입된 `ATCODE_HOME` 아래로 제한한다.

**Tech Stack:** Python 3.11+, 표준 라이브러리(`argparse`, `dataclasses`, `json`, `pathlib`, `subprocess`, `shlex`), tmux, pytest(개발 전용), Bash(설치 스크립트)

## Global Constraints

- 공식 실행 환경은 WSL2와 native Linux이며 Windows 네이티브 실행은 지원하지 않는다.
- Runtime 의존성은 Python 표준 라이브러리만 사용한다.
- 대상 프로젝트에는 AtCode 설정, 상태, Prompt, 로그, Workspace, `.gitignore` 변경을 만들지 않는다.
- `.env`, `.env.local`을 읽거나 수정하지 않는다.
- Phase 1 역할은 `pm`, `developer`, `reviewer`, `tester`, `docs`로 고정한다.
- Phase 1은 `send-keys`, `capture-pane`, Agent Relay, Task Queue, 자동 Workflow를 구현하지 않는다.
- 외부 명령은 `shell=False`와 인자 배열로 실행한다.
- 모든 기능은 실패하는 테스트를 먼저 확인한 뒤 최소 구현한다.

---

## 파일 책임 지도

```text
bin/atcode                         Bash 실행 진입점
src/atcode/__main__.py             Python 모듈 진입점
src/atcode/bootstrap.py            ATCODE_HOME 해석과 의존성 조립
src/atcode/cli.py                  argparse, 출력, 종료 코드
src/atcode/domain/models.py        불변 도메인 값 객체
src/atcode/domain/errors.py        구조화 오류
src/atcode/application/projects.py 프로젝트 탐지와 등록
src/atcode/application/configuration.py 설정 병합과 변경
src/atcode/application/prompts.py  역할 Prompt 렌더링
src/atcode/application/sessions.py 세션 생명주기 조정
src/atcode/application/diagnostics.py doctor와 list 조회
src/atcode/ports/backend.py        TerminalBackend Protocol
src/atcode/ports/adapter.py        AgentAdapter Protocol
src/atcode/ports/storage.py        저장소 Protocol
src/atcode/infrastructure/process.py 안전한 subprocess 경계
src/atcode/infrastructure/tmux_backend.py tmux 구현
src/atcode/infrastructure/adapters/* AI CLI 실행 명세
src/atcode/infrastructure/storage/* JSON 프로젝트·설정·상태 저장
prompts/*.md                       기본 역할 Prompt
scripts/install.sh                 ~/.local/bin 설치
scripts/uninstall.sh               실행 파일 제거와 선택적 데이터 삭제
```

---

### Task 1: 실행 골격과 Runtime 경로

**Files:**
- Create: `pyproject.toml`
- Create: `bin/atcode`
- Create: `src/atcode/__init__.py`
- Create: `src/atcode/__main__.py`
- Create: `src/atcode/bootstrap.py`
- Test: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Produces: `RuntimePaths(home: Path, projects: Path, global_config: Path)`
- Produces: `resolve_runtime_paths(env: Mapping[str, str], install_root: Path) -> RuntimePaths`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_explicit_atcode_home_wins(tmp_path):
    paths = resolve_runtime_paths({"ATCODE_HOME": str(tmp_path)}, Path("/opt/atcode"))
    assert paths.home == tmp_path.resolve()


def test_default_home_is_install_root_data(tmp_path):
    paths = resolve_runtime_paths({}, tmp_path)
    assert paths.home == (tmp_path / "data").resolve()
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: `ModuleNotFoundError` 또는 `resolve_runtime_paths` 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

`RuntimePaths`를 frozen dataclass로 만들고 `ATCODE_HOME` 환경값 또는 `<install_root>/data`를 절대 경로로 해석한다. `bin/atcode`는 `PYTHONPATH=<root>/src`를 설정하고 `python3 -m atcode`를 실행한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_bootstrap.py -q`
Expected: `2 passed`

- [ ] **Step 5: 커밋**

```bash
git add pyproject.toml bin src/atcode/__init__.py src/atcode/__main__.py src/atcode/bootstrap.py tests/unit/test_bootstrap.py
git commit -m "feat: add runtime path bootstrap"
```

### Task 2: 프로젝트 탐지와 등록

**Files:**
- Create: `src/atcode/domain/models.py`
- Create: `src/atcode/domain/errors.py`
- Create: `src/atcode/ports/storage.py`
- Create: `src/atcode/application/projects.py`
- Create: `src/atcode/infrastructure/storage/projects.py`
- Test: `tests/unit/test_projects.py`

**Interfaces:**
- Produces: `Project(project_id: str, name: str, root: Path, created_at: str)`
- Produces: `ProjectStore.list()`, `find_by_id()`, `find_containing()`, `save()`
- Produces: `ProjectService.resolve_root(explicit, cwd)` and `ProjectService.init(explicit, cwd)`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_non_git_project_uses_current_directory(tmp_path, project_service):
    assert project_service.resolve_root(None, tmp_path) == tmp_path.resolve()


def test_registered_parent_beats_nested_current_directory(tmp_path, project_service):
    project = project_service.init(tmp_path, tmp_path)
    nested = tmp_path / "src" / "module"
    nested.mkdir(parents=True)
    assert project_service.resolve_root(None, nested) == project.root


def test_init_writes_only_under_atcode_home(tmp_path, runtime_home, project_service):
    before = set(tmp_path.rglob("*"))
    project_service.init(tmp_path, tmp_path)
    assert set(tmp_path.rglob("*")) == before
    assert any((runtime_home / "projects").iterdir())
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_projects.py -q`
Expected: 프로젝트 모듈 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

명시 경로 → 등록 상위 루트 → Git 루트 → 현재 디렉터리 순서로 해석한다. ID는 정제한 디렉터리 이름과 canonical path의 SHA-256 앞 10자를 결합한다. `project.json`은 원자적으로 저장한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_projects.py -q`
Expected: 모든 프로젝트 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/atcode/domain src/atcode/ports/storage.py src/atcode/application/projects.py src/atcode/infrastructure/storage/projects.py tests/unit/test_projects.py
git commit -m "feat: register projects outside target roots"
```

### Task 3: 설정 병합과 변경

**Files:**
- Create: `src/atcode/application/configuration.py`
- Create: `src/atcode/infrastructure/storage/configuration.py`
- Modify: `src/atcode/domain/models.py`
- Modify: `src/atcode/ports/storage.py`
- Test: `tests/unit/test_configuration.py`

**Interfaces:**
- Produces: `RuntimeConfig(backend: str, roles: Mapping[Role, RoleAssignment])`
- Produces: `ConfigurationService.effective(project)`, `get()`, `set()`, `unset()`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_project_role_override_wins(global_store, project, service):
    global_store.write_global({"schemaVersion": 1, "roles": {"reviewer": {"adapter": "gemini"}}})
    global_store.write_project(project, {"schemaVersion": 1, "roles": {"reviewer": {"adapter": "codex"}}})
    assert service.effective(project).roles[Role.REVIEWER].adapter == "codex"


def test_unknown_role_is_rejected(project, service):
    with pytest.raises(AtCodeError, match="CONFIG_KEY_INVALID"):
        service.set(project, "roles.architect.adapter", "codex", global_scope=False)
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_configuration.py -q`
Expected: 설정 서비스 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

내장 기본값, 전역 JSON, 프로젝트 JSON을 깊이 병합한다. 변경 가능한 키는 `backend`와 `roles.<fixed-role>.adapter`로 제한하고 Backend/Adapter 이름은 Registry allowlist로 검증한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_configuration.py -q`
Expected: 모든 설정 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/atcode/application/configuration.py src/atcode/infrastructure/storage/configuration.py src/atcode/domain/models.py src/atcode/ports/storage.py tests/unit/test_configuration.py
git commit -m "feat: merge global and project configuration"
```

### Task 4: Prompt 렌더링

**Files:**
- Create: `src/atcode/application/prompts.py`
- Create: `prompts/pm.md`
- Create: `prompts/developer.md`
- Create: `prompts/reviewer.md`
- Create: `prompts/tester.md`
- Create: `prompts/docs.md`
- Test: `tests/unit/test_prompts.py`

**Interfaces:**
- Produces: `PromptRenderer.render(project, role, atcode_home) -> RenderedPrompt`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_prompt_is_rendered_only_under_runtime_home(tmp_path, project, renderer):
    rendered = renderer.render(project, Role.DEVELOPER, tmp_path)
    assert rendered.path.is_relative_to(tmp_path)
    assert str(project.root) in rendered.text
    assert not (project.root / ".atcode").exists()


def test_unknown_template_token_fails(project, renderer_with_bad_template, tmp_path):
    with pytest.raises(AtCodeError, match="PROMPT_TOKEN_UNKNOWN"):
        renderer_with_bad_template.render(project, Role.PM, tmp_path)
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_prompts.py -q`
Expected: Prompt Renderer 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

허용된 다섯 토큰만 문자열 치환하고 결과를 `ATCODE_HOME/projects/<id>/workspace/prompts/<role>.md`에 원자적으로 저장한다. 템플릿에는 역할 책임과 대상 프로젝트 무흔적 원칙을 한국어로 명시한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_prompts.py -q`
Expected: 모든 Prompt 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/atcode/application/prompts.py prompts tests/unit/test_prompts.py
git commit -m "feat: render role prompts in runtime workspace"
```

### Task 5: Process 경계와 AI Adapter

**Files:**
- Create: `src/atcode/ports/adapter.py`
- Create: `src/atcode/infrastructure/process.py`
- Create: `src/atcode/infrastructure/adapters/registry.py`
- Create: `src/atcode/infrastructure/adapters/shell.py`
- Create: `src/atcode/infrastructure/adapters/codex.py`
- Create: `src/atcode/infrastructure/adapters/claude.py`
- Create: `src/atcode/infrastructure/adapters/gemini.py`
- Test: `tests/unit/test_adapters.py`

**Interfaces:**
- Produces: `AgentAdapter.probe() -> DiagnosticResult`
- Produces: `AgentAdapter.build_launch(context) -> LaunchSpec`
- Produces: `AdapterRegistry.get(name) -> AgentAdapter`

- [ ] **Step 1: 공식 실행 규약 확인**

Codex는 OpenAI 공식 문서, Claude와 Gemini는 각 공식 CLI 문서 및 설치된 `--help`를 확인한다. 대화형 세션을 유지하면서 최초 Prompt를 전달하는 옵션만 채택하고 권한 우회 옵션은 사용하지 않는다.

- [ ] **Step 2: 실패 테스트 작성**

```python
@pytest.mark.parametrize("name", ["codex", "claude", "gemini", "shell"])
def test_registry_returns_supported_adapter(name, registry):
    assert registry.get(name).name == name


def test_launch_spec_uses_argument_array(context, codex_adapter):
    spec = codex_adapter.build_launch(context)
    assert spec.executable == "codex"
    assert isinstance(spec.arguments, tuple)
    assert context.prompt.text in spec.arguments
```

- [ ] **Step 3: RED 확인**

Run: `python -m pytest tests/unit/test_adapters.py -q`
Expected: Adapter 모듈 미정의로 FAIL

- [ ] **Step 4: 최소 구현**

각 Adapter는 executable 탐지와 안전한 `LaunchSpec` 생성만 담당한다. Shell은 로그인 셸을 실행하고 Prompt 경로를 환경변수로 제공한다.

- [ ] **Step 5: GREEN 확인**

Run: `python -m pytest tests/unit/test_adapters.py -q`
Expected: 모든 Adapter 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add src/atcode/ports/adapter.py src/atcode/infrastructure/process.py src/atcode/infrastructure/adapters tests/unit/test_adapters.py
git commit -m "feat: add safe AI CLI adapters"
```

### Task 6: tmux Backend

**Files:**
- Create: `src/atcode/ports/backend.py`
- Create: `src/atcode/infrastructure/tmux_backend.py`
- Modify: `src/atcode/domain/models.py`
- Test: `tests/unit/test_tmux_backend.py`

**Interfaces:**
- Produces: `TerminalBackend` Protocol
- Produces: `TmuxBackend.create_session()`, `inspect_session()`, `attach_session()`, `terminate_session()`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_create_session_builds_role_windows(fake_runner, backend, session_spec):
    backend.create_session(session_spec)
    commands = [call.argv for call in fake_runner.calls]
    assert commands[0][:3] == ("tmux", "has-session", "-t")
    assert any("new-session" in command for command in commands)
    assert sum("new-window" in command for command in commands) == 4


def test_partial_creation_rolls_back_only_new_session(fake_runner_failing_on_window, backend, session_spec):
    with pytest.raises(AtCodeError):
        backend.create_session(session_spec)
    assert any("kill-session" in call.argv for call in fake_runner_failing_on_window.calls)
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_tmux_backend.py -q`
Expected: Backend 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

tmux 식별자를 정규식으로 검증하고 `subprocess` 인자 배열만 사용한다. Window 실행 문자열은 `env ... <executable> <args>` 배열을 `shlex.join()`으로 한 번 직렬화한다. Pane 출력 및 입력 API는 구현하지 않는다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_tmux_backend.py -q`
Expected: 모든 Backend 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/atcode/ports/backend.py src/atcode/infrastructure/tmux_backend.py src/atcode/domain/models.py tests/unit/test_tmux_backend.py
git commit -m "feat: manage project sessions through tmux"
```

### Task 7: 상태 저장과 Session Service

**Files:**
- Create: `src/atcode/infrastructure/storage/state.py`
- Create: `src/atcode/application/sessions.py`
- Modify: `src/atcode/ports/storage.py`
- Modify: `src/atcode/domain/models.py`
- Test: `tests/unit/test_sessions.py`

**Interfaces:**
- Produces: `StateStore.read()`, `write()`, `locked()`
- Produces: `SessionService.start()`, `attach()`, `stop()`, `status()`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_start_preflights_all_adapters_before_backend_create(session_service, missing_adapter, backend):
    with pytest.raises(AtCodeError, match="ADAPTER_NOT_FOUND"):
        session_service.start()
    assert backend.created_specs == []


def test_stop_is_idempotent(session_service, backend):
    backend.snapshot = SessionSnapshot.stopped()
    result = session_service.stop()
    assert result.status is Lifecycle.STOPPED
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/unit/test_sessions.py -q`
Expected: Session Service 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

모든 Prompt, Adapter, Backend 검증을 통과한 뒤에만 세션을 생성한다. 상태 파일은 임시 파일과 `os.replace()`로 저장하고 프로젝트별 파일 잠금으로 lifecycle mutation을 직렬화한다. 실제 상태는 항상 Backend snapshot을 기준으로 한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/unit/test_sessions.py -q`
Expected: 모든 Session 테스트 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/atcode/infrastructure/storage/state.py src/atcode/application/sessions.py src/atcode/ports/storage.py src/atcode/domain/models.py tests/unit/test_sessions.py
git commit -m "feat: coordinate idempotent session lifecycle"
```

### Task 8: CLI, doctor, list

**Files:**
- Create: `src/atcode/application/diagnostics.py`
- Create: `src/atcode/cli.py`
- Modify: `src/atcode/bootstrap.py`
- Modify: `src/atcode/__main__.py`
- Test: `tests/integration/test_cli.py`

**Interfaces:**
- Produces: eight public subcommands and config operations from the design spec

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_init_creates_runtime_project_without_touching_target(cli, tmp_path, runtime_home):
    before = set(tmp_path.rglob("*"))
    result = cli("init", "--project", str(tmp_path))
    assert result.exit_code == 0
    assert set(tmp_path.rglob("*")) == before
    assert list((runtime_home / "projects").iterdir())


def test_doctor_reports_missing_adapter_without_traceback(cli_with_missing_adapter):
    result = cli_with_missing_adapter("doctor")
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    assert "Traceback" not in result.stderr
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: CLI 미정의 또는 명령 미지원으로 FAIL

- [ ] **Step 3: 최소 구현**

`argparse` parser와 얇은 명령 handler를 구현하고 Application service 결과만 한국어로 출력한다. `AtCodeError`는 code/message/hint 형태로 출력하고 exit class 1 또는 2로 변환한다. `doctor`는 환경을 수정하지 않는다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/integration/test_cli.py -q`
Expected: 모든 CLI 통합 테스트 PASS

- [ ] **Step 5: 전체 테스트 확인**

Run: `python -m pytest -q`
Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add src/atcode/application/diagnostics.py src/atcode/cli.py src/atcode/bootstrap.py src/atcode/__main__.py tests/integration/test_cli.py
git commit -m "feat: expose phase 1 runtime commands"
```

### Task 9: 설치, 한국어 문서, 실제 검증

**Files:**
- Create: `scripts/install.sh`
- Create: `scripts/uninstall.sh`
- Create: `README.md`
- Create: `.gitignore`
- Test: `tests/integration/test_install_scripts.py`
- Test: `tests/integration/test_no_target_artifacts.py`

**Interfaces:**
- Produces: `~/.local/bin/atcode` 설치와 제거
- Produces: `scripts/uninstall.sh --purge-data` 확인형 데이터 제거

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_uninstall_preserves_runtime_data_by_default(run_script, temp_home, runtime_home):
    marker = runtime_home / "keep-me"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("keep")
    run_script("scripts/uninstall.sh", env={"HOME": str(temp_home), "ATCODE_HOME": str(runtime_home)})
    assert marker.exists()


def test_full_lifecycle_leaves_target_tree_unchanged(runtime_cli, target_project):
    before = snapshot(target_project)
    runtime_cli.init(target_project)
    runtime_cli.start_with_fake_backend(target_project)
    runtime_cli.status(target_project)
    runtime_cli.stop(target_project)
    assert snapshot(target_project) == before
```

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/integration/test_install_scripts.py tests/integration/test_no_target_artifacts.py -q`
Expected: 스크립트 및 lifecycle fixture 미정의로 FAIL

- [ ] **Step 3: 최소 구현**

설치 스크립트는 `~/.local/bin/atcode` 심볼릭 링크만 생성한다. 제거 스크립트는 링크만 제거하며 `--purge-data`일 때 정확한 경로를 보여주고 대화형 확인 후 Runtime data만 제거한다. README는 설치, 설정, 기본 흐름, Phase 1 제한을 한국어로 설명한다.

- [ ] **Step 4: 전체 검증**

Run: `python -m pytest -q`
Expected: 모든 테스트 PASS

Run: `python -m compileall -q src tests`
Expected: exit 0

Run on WSL/Linux when available: `bash -n bin/atcode scripts/install.sh scripts/uninstall.sh`
Expected: exit 0

Run on WSL/Linux with tmux when available: `python -m pytest tests/integration -m tmux -q`
Expected: tmux integration tests PASS, or explicit environment-based skip when tmux is unavailable

- [ ] **Step 5: 보안 및 범위 검토**

Run: `git diff --check`
Expected: no output

Run: `git diff --cached --name-only`
Expected: `.env` 파일과 target-project 파일이 없음

- [ ] **Step 6: 커밋**

```bash
git add scripts README.md .gitignore tests/integration
git commit -m "docs: add installation and usage workflow"
```

---

## 최종 Checkpoint

- [ ] `python -m pytest -q` 전체 PASS
- [ ] `python -m compileall -q src tests` PASS
- [ ] 대상 프로젝트 무흔적 통합 테스트 PASS
- [ ] tmux가 있는 WSL/Linux에서 실제 5개 Window lifecycle 검증
- [ ] `atcode doctor`가 누락된 CLI를 세션 생성 전에 표시
- [ ] `atcode start`와 `atcode stop` 반복 실행이 멱등
- [ ] `.env`, `.env.local`, AI 출력, 사용자 작업 내용이 Runtime 상태에 저장되지 않음
- [ ] Git 작업 트리에 의도하지 않은 파일이 없음
