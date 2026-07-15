# Spec: 비개발자용 WSL 안내형 설치

## 가정

1. Phase 1의 주 사용 환경은 Windows 10/11의 WSL2 Ubuntu이며, 일반 Linux도 같은 설치 흐름을 사용할 수 있다.
2. 사용자는 AtCode 저장소를 이미 내려받았고, WSL에서 그 디렉터리로 이동할 수 있다.
3. 일반 사용자는 Python 가상환경, `pip`, `pytest`를 설치할 필요가 없다. 이 도구들은 AtCode 개발자에게만 필요하다.
4. 시스템 패키지 설치, 공식 Codex 설치 스크립트 실행, 로그인, 셸 설정 변경은 사용자 확인 없이 수행하지 않는다.
5. Phase 1에서는 PowerShell·Git Bash 전용 설치기와 WSL 자체 자동 설치를 제공하지 않는다.

## Objective

비개발자도 WSL 터미널에서 다음 명령 하나로 AtCode 실행 준비를 끝낼 수 있는 안내형 설치기를 만든다.

```bash
cd /mnt/d/myproject/AtCode
bash scripts/install.sh
```

설치기는 환경을 검사하고, 필요한 조치가 있으면 한국어로 이유와 실행 명령을 보여준 뒤 동의를 구한다. 준비가 끝나면 `atcode` 실행 파일을 설치하고 `atcode doctor`를 실행한다.

성공한 사용자는 이후 작업 프로젝트에서 다음 명령만 알면 된다.

```bash
cd /mnt/d/project/SmileLRS
atcode init
atcode start
atcode attach
```

## 검토한 접근

### A. 안내형 단일 설치기 — 채택

기존 `scripts/install.sh`가 사전 점검, 선택적 설치, 로그인 안내, launcher 설치, 최종 진단을 순서대로 수행한다. 별도 설치 프레임워크나 Python 의존성을 추가하지 않는다.

- 장점: 사용 명령이 하나이며 현재 Bash 기반 구조를 유지한다.
- 장점: 실제 실패 지점에서 바로 복구 방법을 제공할 수 있다.
- 단점: Bash 함수가 늘어나므로 함수별 책임과 테스트 경계를 지켜야 한다.

### B. 문서만 상세화 — 제외

README에 명령을 나열하고 사용자가 직접 순서대로 실행한다.

- 장점: 코드 변경이 가장 작다.
- 단점: `PATH`, Windows용 Codex 오인식, 로그인 누락 같은 실수를 예방하지 못한다.

### C. 별도 Python 설치 마법사 — 제외

Python 프로그램이 설치 상태를 관리하고 Bash는 이를 호출한다.

- 장점: 복잡한 상태 관리에는 유리하다.
- 단점: Python 자체가 없거나 버전이 낮은 환경을 처리하기 어렵고, Phase 1 범위에 비해 구조가 과하다.

## 사용자 흐름

설치기는 아래 순서를 따른다. 각 단계는 `[PASS]`, `[WARN]`, `[FAIL]` 중 하나로 표시한다.

1. **실행 환경 확인**
   - Linux 또는 WSL인지 확인한다.
   - Git Bash나 Windows에서 실행하면 즉시 중단하고 PowerShell에서 `wsl -d Ubuntu`를 실행하라고 안내한다.
   - WSL 배포판 설치나 활성화는 자동화하지 않는다.

2. **Python 확인**
   - `python3` 존재 여부와 Python 3.11 이상인지 확인한다.
   - 조건을 충족하지 못하면 자동 업그레이드하지 않고 배포판에 맞는 복구 안내와 함께 중단한다.
   - `venv`, `pip`, `pytest`는 검사하거나 설치하지 않는다.

3. **tmux 확인**
   - `tmux -V`가 성공하면 건너뛴다.
   - Ubuntu/Debian 계열에서 누락되면 `sudo apt update`와 `sudo apt install -y tmux`를 실행해도 되는지 묻는다.
   - 거절하면 명령을 복사할 수 있게 보여주고 중단한다.
   - 지원 여부를 확신할 수 없는 배포판에서는 패키지 관리자를 추측해 실행하지 않는다.

4. **Codex 확인**
   - `command -v codex`뿐 아니라 `codex --version` 성공 여부까지 검사한다.
   - 경로가 `/mnt/c/`, `/mnt/d/`처럼 Windows 드라이브 아래라면 WSL 네이티브 Codex가 아닌 것으로 판단한다. 기존 Windows 설치는 삭제하지 않고 WSL용 설치를 안내한다.
   - Codex가 없거나 실행되지 않으면 고정된 공식 URL `https://chatgpt.com/codex/install.sh`의 설치 스크립트를 실행해도 되는지 묻는다.
   - 동의한 경우에만 공식 설치 명령을 실행한다. 원격 URL을 인자나 설정으로 받지 않는다.
   - 설치 후 `~/.local/bin/codex --version` 또는 새로 탐지한 실행 파일로 다시 검증한다.

5. **PATH 확인**
   - 현재 프로세스에서는 `~/.local/bin`을 기존 `PATH` 앞에 안전하게 추가한다.
   - 셸을 다시 열어도 적용되도록 `~/.bashrc`에 정확한 한 줄을 추가해도 되는지 묻는다.

     ```bash
     export PATH="$HOME/.local/bin:$PATH"
     ```

   - 같은 설정이 이미 있으면 추가하지 않는다.
   - `%PATH` 같은 Windows 문법을 제시하지 않는다.
   - 사용자가 변경을 거절하면 이번 설치는 계속하되, 마지막에 수동 명령을 안내한다.

6. **Codex 로그인 확인**
   - `codex login status`의 종료 상태와 출력을 확인한다.
   - 로그인되지 않았다면 `codex login`을 실행해도 되는지 묻는다.
   - 동의한 경우 대화형 로그인을 현재 터미널에 연결한다.
   - 일반 로그인에 실패하면 `codex login --device-auth`를 대안으로 안내한다.
   - 토큰, 로그인 결과 원문, 인증 파일은 AtCode가 저장하거나 복사하지 않는다.

7. **AtCode launcher 설치**
   - `~/.local/bin/atcode`가 저장소의 `bin/atcode`를 호출하도록 설치한다.
   - 같은 저장소를 대상으로 다시 실행해도 안전하게 갱신한다.
   - Runtime 데이터 위치는 기존처럼 `bin/atcode`가 `ATCODE_HOME` 또는 `<atcode>/data`로 결정한다.

8. **최종 진단과 다음 명령 표시**
   - 프로젝트를 등록하지 않은 상태에서 `atcode doctor`를 실행한다.
   - 실패하면 실패 항목과 복구 방법을 그대로 보여주고 비정상 종료한다.
   - 성공하면 작업 프로젝트로 이동한 뒤 실행할 `atcode init`, `atcode start`, `atcode attach`를 표시한다.

## 명령 인터페이스

### 일반 사용자

```bash
bash scripts/install.sh
```

대화형 질문에는 `y`, `Y`, `yes`만 동의로 처리하며 그 외 입력은 거절로 처리한다. 입력이 터미널에 연결되지 않은 경우 시스템 변경을 시도하지 않고 필요한 조건을 설명하며 실패한다.

### 개발 및 기존 테스트

```bash
bash scripts/install.sh --launcher-only
```

`--launcher-only`는 사전 조건 설치, 로그인, `.bashrc` 변경 없이 launcher만 설치한다. CI, 개발 테스트, 이미 준비된 고급 사용자만을 위한 명시적 우회로다. 알 수 없는 옵션은 사용법과 함께 실패한다.

### 제거

기존 인터페이스를 유지한다.

```bash
bash scripts/uninstall.sh
bash scripts/uninstall.sh --purge-data
```

## Architecture

이번 변경은 설치 경험에만 집중한다. Runtime의 Port, Adapter, Backend 구조는 변경하지 않는다.

```text
scripts/install.sh
  ├─ 환경 검사 함수
  ├─ 사용자 확인 함수
  ├─ 선택적 의존성 준비 함수
  ├─ PATH 영구 설정 함수
  ├─ launcher 설치 함수
  └─ 최종 doctor 실행

bin/atcode
  └─ ATCODE_HOME 설정 + Python Runtime 실행

src/atcode/cli.py
  └─ doctor의 FAIL/WARN hint 출력
```

`install.sh`는 설치 오케스트레이션만 담당하고, 프로젝트 등록이나 Runtime 상태 생성을 직접 수행하지 않는다. `doctor`는 계속 읽기 전용 진단 명령으로 유지한다.

## Project Structure

```text
scripts/install.sh
  안내형 설치 진입점과 launcher-only 모드

src/atcode/cli.py
  doctor 결과의 실행 가능한 hint 출력

tests/integration/test_install_scripts.py
  실제 사용자 홈 대신 임시 HOME과 가짜 명령을 사용하는 설치 시나리오 테스트

tests/integration/test_cli.py
  doctor hint 출력 계약 테스트

README.md
  비개발자 중심 설치와 첫 실행 절차

docs/superpowers/specs/2026-07-15-guided-wsl-installer-design.md
  이 설계의 기준 문서
```

필요한 경우 설치 테스트용 작은 fixture나 가짜 실행 파일은 `tests/fixtures/` 아래에 둔다. 제품 코드에 테스트 전용 분기를 추가하지 않는다.

## Code Style

Bash 함수는 한 가지 책임만 갖고, 전역 상태보다 명시적인 종료 상태를 사용한다. 외부 명령과 경로는 항상 인용한다.

```bash
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

- 함수와 변수 이름은 현재 스크립트처럼 `snake_case`, `UPPER_SNAKE_CASE`를 사용한다.
- 사용자 메시지는 짧고 자연스러운 한국어로 작성한다.
- `eval`, 문자열로 조립한 셸 명령, 무검증 원격 URL은 사용하지 않는다.
- 실패 메시지는 원인, 사용자가 할 일, 다시 실행할 명령을 포함한다.

## 오류 처리

- 사전 조건 실패는 해당 단계에서 멈추며, Python traceback이나 불필요한 내부 경로를 노출하지 않는다.
- 사용자가 시스템 변경을 거절한 것은 오류가 아니라 안전한 중단으로 설명하되, 설치가 완료되지 않았으므로 0이 아닌 종료 코드를 반환한다.
- `tmux`나 Codex 설치 명령이 실패하면 다음 단계로 넘어가지 않는다.
- `.bashrc` 변경 실패는 현재 셸에서 실행이 가능하면 경고로 처리하고 수동 설정 명령을 표시한다.
- launcher 설치 후 최종 `doctor`가 실패하면 launcher를 자동 삭제하지 않는다. 문제를 고친 뒤 설치기나 `atcode doctor`를 다시 실행할 수 있다.
- 대상 작업 프로젝트에는 파일, 로그, 설정, `.gitignore`, Workspace를 만들지 않는다.

## 보안 모델

신뢰 경계는 터미널 입력, 운영체제 패키지 관리자, HTTPS로 내려받는 공식 Codex 설치 스크립트, Codex 로그인 절차다. 보호할 자산은 사용자의 시스템 권한, 셸 설정, Codex 인증 정보, AtCode 및 작업 프로젝트 파일이다.

주요 오용 사례와 대응:

- 사용자가 입력한 값을 셸 명령으로 실행하는 문제: 확인 응답은 허용된 문자열과만 비교하며 명령 인자로 사용하지 않는다.
- 임의 URL의 스크립트를 실행하는 문제: 소스 코드에 고정된 HTTPS 공식 URL만 사용하고 실행 전 정확한 URL과 작업을 표시한다.
- 의도하지 않은 권한 상승: `sudo` 명령은 tmux 설치에만 사용하며 별도 동의 없이는 호출하지 않는다.
- Windows 실행 파일을 WSL 네이티브 CLI로 오인하는 문제: `/mnt/<drive>/...` 경로와 실제 버전 명령을 함께 검사한다.
- 인증 정보 노출: 로그인은 Codex CLI에 직접 맡기며 stdout을 파일에 기록하거나 Runtime 상태에 저장하지 않는다.
- 셸 설정 변조 또는 중복: 추가할 PATH 줄을 고정하고, 정확한 기존 줄을 먼저 검색한 뒤 한 번만 추가한다.

설치기는 범용 명령 실행기나 URL 다운로드 도구가 아니다. 사용자가 입력한 경로, URL, 패키지 이름을 `sudo`, `curl`, `bash`에 전달하는 인터페이스를 만들지 않는다.

## Testing Strategy

테스트는 실제 `sudo`, 네트워크, 로그인, 사용자의 `.bashrc`를 건드리지 않는다. 임시 `HOME`, 제한된 `PATH`, 가짜 `tmux`·`codex` 실행 파일과 표준 입력을 사용한다.

필수 시나리오:

1. 준비된 Linux 환경에서는 모든 설치 단계를 건너뛰고 launcher와 최종 진단이 성공한다.
2. `--launcher-only`는 Git Bash를 포함한 테스트 환경에서 기존 launcher 설치·제거 계약을 유지한다.
3. Python이 없거나 3.11 미만이면 명확히 실패한다.
4. tmux가 없으면 동의를 묻고, 비대화형 또는 거절 시 시스템 명령을 실행하지 않는다.
5. `/mnt/c/.../codex`가 잡히면 정상 설치로 오인하지 않는다.
6. 경로에 Codex가 있어도 `codex --version` 실패 시 설치되지 않은 것으로 처리한다.
7. 로그인되지 않은 경우 동의를 받기 전에는 `codex login`을 실행하지 않는다.
8. `.bashrc` PATH 설정을 여러 번 실행해도 같은 줄이 중복되지 않는다.
9. 설치 전후 대상 프로젝트의 파일 목록은 변하지 않는다.
10. `doctor`의 FAIL/WARN 결과에 hint가 있으면 화면에 함께 출력한다.

검증 명령:

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

실제 WSL 수동 검증은 깨끗한 임시 `HOME` 또는 테스트 사용자에서 수행하며 다음을 확인한다.

```bash
bash scripts/install.sh
command -v atcode
command -v codex
codex login status
atcode doctor
```

## Boundaries

### Always

- WSL/Linux 여부, Python 버전, tmux 실행, Codex 실제 실행, Codex 로그인 상태를 순서대로 검증한다.
- 외부 변경 전에 수행할 명령과 이유를 보여주고 확인을 받는다.
- 설치기를 재실행해도 안전하고 `.bashrc` 설정이 중복되지 않게 한다.
- 테스트에서는 실제 시스템과 사용자 인증 상태를 변경하지 않는다.
- Runtime 데이터는 `ATCODE_HOME`을 통해서만 접근한다.

### Ask first

- `sudo apt`로 시스템 패키지를 설치하는 작업
- 공식 Codex 원격 설치 스크립트를 내려받아 실행하는 작업
- `~/.bashrc`를 수정하는 작업
- 대화형 `codex login`을 실행하는 작업

### Never

- WSL 또는 Linux 배포판 자체를 자동 설치하거나 재설정하지 않는다.
- 사용자 동의 없이 `sudo`, 원격 스크립트, 로그인, 셸 설정 변경을 실행하지 않는다.
- 프로젝트 저장소 안에 AtCode 설정, 상태, 로그, Workspace, `.gitignore` 변경을 만들지 않는다.
- 인증 토큰이나 자격 증명을 읽거나 저장하지 않는다.
- Python 가상환경, `pip`, `pytest`를 일반 설치 요구 사항에 포함하지 않는다.
- PowerShell/Git Bash 설치기, 자동 업데이트, Telemetry를 이번 범위에 추가하지 않는다.

## Success Criteria

1. 준비된 WSL2 Ubuntu 사용자는 `bash scripts/install.sh` 한 번으로 launcher 설치와 `atcode doctor`까지 완료한다.
2. 누락된 tmux, WSL용 Codex, 로그인, PATH 설정은 발생한 단계에서 한국어로 안내된다.
3. 모든 시스템·계정·셸 변경은 실행 전에 명시적으로 동의를 받는다.
4. Windows 드라이브의 Codex 또는 실행 불가능한 Codex를 정상으로 잘못 판정하지 않는다.
5. 설치기를 여러 번 실행해도 launcher와 `.bashrc`가 손상되거나 중복되지 않는다.
6. 일반 사용법에는 가상환경과 테스트 도구가 등장하지 않는다.
7. 설치와 진단 과정은 작업 대상 프로젝트에 어떤 흔적도 남기지 않는다.
8. 기존 71개 테스트와 새 설치 시나리오 테스트가 모두 통과한다.

## 확장 경계

- Phase 2의 pane layout, Agent 메시지 전달, 역할 수정은 이 설치 변경과 독립적으로 유지한다.
- 향후 Claude·Gemini 선택형 설치가 필요하면 `CLI 준비 상태 검사`를 별도 인터페이스로 승격할 수 있다. Phase 1에서는 기본 역할이 모두 Codex이므로 Codex만 안내 설치한다.
- 배포 단계에서 패키지 설치기가 생기면 launcher 설치 함수만 교체하고 Runtime의 `ATCODE_HOME` 계약은 유지한다.

## Open Questions

없음. 구현 중 운영체제별 패키지 설치 차이가 발견되면 지원 대상을 넓히지 않고, WSL2 Ubuntu/Debian 흐름을 우선 완성한 뒤 별도 설계로 다룬다.
