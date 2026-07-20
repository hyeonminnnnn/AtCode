# AtCode

AtCode는 Codex, Claude, Gemini 같은 AI CLI를 역할 기반 개발팀으로 실행하는 Runtime입니다. 현재 WSL2와 Linux에서 tmux를 Backend로 사용합니다.

## 핵심 원칙

- AtCode 설정, 상태, Prompt, Workspace는 `ATCODE_HOME`에만 저장합니다.
- 실제 작업 대상 프로젝트에는 AtCode 관리 파일을 만들지 않습니다.
- AI CLI는 사용자가 지시한 개발 작업에 따라 대상 프로젝트 소스를 수정할 수 있습니다.
- 역할 전달에는 tmux pane의 현재 출력을 일시적으로 읽지만 전체 대화나 출력 이력을 파일로 저장하지 않습니다.

## 요구 환경

- Python 3.11 이상
- WSL2 또는 Linux
- tmux
- 역할에 배정할 Codex, Claude, Gemini CLI 중 필요한 명령

## 설치

WSL에서 AtCode 저장소로 이동해 안내형 설치기를 실행합니다.

```bash
cd /mnt/d/myproject/AtCode
bash scripts/install.sh
```

설치기는 Python, tmux, WSL/Linux용 Codex, PATH, 로그인 상태를 순서대로
확인합니다. 시스템 패키지 설치, 공식 Codex 설치, `.bashrc` 수정, 로그인은 실행
전에 동의를 구합니다. 마지막에는 `atcode doctor`를 자동 실행합니다.

화면에 `source "$HOME/.bashrc"`가 표시되면 한 번 실행해 현재 터미널에 PATH를
적용합니다. 일반 사용에는 Python 가상환경, pip, pytest가 필요하지 않습니다.

개발 단계의 기본 Runtime 위치는 AtCode 저장소의 `data/`입니다. 다른 위치를 사용하려면 절대 경로를 지정합니다.

```bash
export ATCODE_HOME="$HOME/.local/share/atcode"
```

## 기본 사용법

```bash
cd /mnt/d/project/SmileLRS
atcode init
atcode doctor
atcode start
atcode attach
```

기본 화면은 `team` 창 하나를 PM, Developer, Reviewer 세 pane으로 나눕니다.
먼저 PM에게 작업을 지시합니다. 현재 역할이 응답 마지막에 handoff 블록을 만들면
`Ctrl+b Enter`를 눌러 다음 역할로 전달합니다.

```text
PM → Developer → Reviewer → PM
```

`Ctrl+b Enter`를 다른 tmux 기능이 이미 사용 중이면 AtCode가 덮어쓰지 않고
경고합니다. 이때는 같은 동작을 명령으로 실행합니다.

```bash
atcode next
```

pane 사이를 이동하려면 `Ctrl+b`를 누른 뒤 방향키를 누릅니다. 선택한 pane을
크게 보거나 원래 화면으로 돌아가려면 `Ctrl+b z`를 누릅니다.

tmux에서 빠져나오려면 `Ctrl+b d`를 누릅니다. detach한 뒤에는 다음 명령으로
상태를 확인하거나 세션을 종료할 수 있습니다.

```bash
atcode status
atcode stop
```

다른 위치에서는 프로젝트 경로를 명시할 수도 있습니다.

```bash
atcode status --project /mnt/d/project/SmileLRS
```

## 여러 세션 열기

AtCode는 프로젝트 하나당 tmux 세션 하나를 만듭니다. 여러 프로젝트를 동시에
사용하려면 각 WSL 터미널에서 작업할 프로젝트 루트로 이동한 뒤 AtCode를
실행합니다. `PROJECT_ID`나 tmux 세션명을 직접 계산하실 필요는 없습니다.

첫 번째 WSL 터미널:

```bash
cd /mnt/d/project/SmileLRS
atcode init       # 이 프로젝트에서 최초 한 번만 실행합니다.
atcode start
atcode attach
```

두 번째 WSL 터미널:

```bash
cd /mnt/d/project/AnotherProject
atcode init       # 이 프로젝트에서 최초 한 번만 실행합니다.
atcode start
atcode attach
```

등록된 프로젝트와 실행 상태는 어느 위치에서든 다음 명령으로 확인할 수 있습니다.

```bash
atcode list
```

특정 프로젝트의 상태를 확인하거나 세션을 종료할 때는 해당 프로젝트 루트로
이동해서 명령을 실행합니다. 이동하지 않으려면 `--project`에 절대 경로를
지정합니다.

```bash
atcode status --project /mnt/d/project/SmileLRS
atcode stop --project /mnt/d/project/SmileLRS
```

같은 프로젝트에서 `atcode attach`를 여러 번 실행하면 새 AtCode 세션이 생기는
것이 아니라 기존 tmux 세션을 함께 사용합니다. 프로젝트 하나에 서로 독립된
workflow 여러 개를 만드는 기능은 현재 지원하지 않습니다.

기본 3-pane 화면에서는 PM, Developer, Reviewer를 동시에 볼 수 있습니다.
역할별 창을 하나씩 사용하는 방식이 더 편하다면 다음과 같이 설정한 뒤 세션을
다시 시작합니다.

```bash
cd /mnt/d/project/SmileLRS
atcode config set layout windows
atcode stop
atcode start
atcode attach
```

3-window 화면에서는 `Ctrl+b n`과 `Ctrl+b p`로 다음·이전 역할 창으로 이동하고,
`Ctrl+b w`로 창 목록을 열 수 있습니다.

## 역할과 Adapter

AtCode Runtime은 다음 세 역할의 단일 Workflow를 사용합니다.

```text
PM → Developer → Reviewer → PM
```

역할 책임:

```text
PM         요구사항 분석, 완료 조건, 작업 배분, 결과 확인, 최종 정리
Developer  프로젝트에 필요한 프론트엔드·백엔드·디자인·문서 구현
Reviewer   코드 리뷰, 과설계 점검, 테스트 실행과 최종 검증
```

Developer는 고정된 Frontend·Backend 역할로 나뉘지 않습니다. 프로젝트와 PM Brief를
읽고 필요한 전문 영역을 판단합니다. 병렬 작업이 실제로 필요하면 향후 Developer가
독립 작업과 통합 순서를 제안하고, PM 또는 사용자 승인 후에만 임시 Team을 만드는
방향으로 확장합니다.

세 역할의 기본 Adapter는 모두 Codex입니다. Claude, Gemini, Shell Adapter 지원은
유지되므로 필요한 CLI가 설치되어 있다면 역할별로 변경할 수 있습니다.

각 역할 Prompt에는 특정 AI 모델의 스킬 이름이나 호출 문법 대신 요구사항 명세,
점진적 구현, 테스트 우선 개발, 품질·과설계 검토, 증거 중심 테스트, 문서화와
한국어 윤문 절차가 자연어로 포함됩니다. 따라서 다른 Adapter를 선택해도 같은 역할
Prompt를 사용할 수 있습니다.

기존 5역할 세션은 다음 순서로 세 역할 세션으로 전환합니다. 기존 tmux 대화 내용은
세션 종료와 함께 사라집니다.

```bash
atcode status
atcode stop
atcode start
atcode attach
```

프로젝트별 변경:

```bash
atcode config set roles.reviewer.adapter codex
atcode config show
```

기본 3-pane 대신 역할별 3-window 화면을 사용하려면 설정 후 세션을 다시 만듭니다.
실행 중인 화면을 즉시 변환하지는 않습니다.

```bash
atcode config set layout windows
atcode stop
atcode start
```

전역 기본값 변경:

```bash
atcode config set roles.developer.adapter codex --global
```

Adapter는 각 CLI의 공식 대화형 최초 Prompt 규약을 사용합니다.

- [Codex CLI 명령 참고](https://developers.openai.com/codex/cli/reference/)
- [Claude Code CLI 참고](https://code.claude.com/docs/en/cli-usage)
- [Gemini CLI 참고](https://geminicli.com/docs/cli/cli-reference/)

## 명령

```text
atcode init
atcode start
atcode attach
atcode next
atcode stop
atcode status
atcode doctor
atcode config
atcode list
```

## 전달 상태와 재시작

`atcode status`는 tmux 세션과 함께 현재 workflow 역할, round, 최근 transfer와
delivery 상태를 표시합니다.

```bash
atcode status
```

컴퓨터를 재부팅하거나 tmux 세션이 사라진 뒤 `atcode start`를 실행하면 역할 Prompt를
다시 만들고 현재 역할에 최신 전달 내용 하나를 복원합니다. 전체 대화 내용은 복원하지
않습니다.

이전 workflow를 버리고 처음부터 시작하려면 먼저 세션을 종료한 뒤 `--fresh`를
사용합니다. 현재 상태를 보여준 뒤 `y` 또는 `yes`를 입력해야 초기화됩니다.

```bash
atcode stop
atcode start --fresh
```

역할 Prompt 파일에는 역할 계약만 저장되며 handoff가 계속 쌓이지 않습니다. 현재
workflow는 `workspace/workflow.json`, 최신 handoff 하나는
`workspace/handoff.json`에 저장됩니다. 이 파일을 포함한 모든 Runtime 데이터는
`ATCODE_HOME` 아래에만 존재합니다.

전달은 장애 복구를 위해 같은 transfer ID가 다시 입력될 수 있습니다. 역할 Prompt는
이미 처리한 transfer ID의 작업을 중복 수행하지 않도록 지시합니다.

## 현재 범위

- 프로젝트당 활성 workflow 하나
- PM → Developer → Reviewer → PM 고정 순서
- Reviewer 승인 시 완료, 반려 시 PM을 거쳐 Developer 재작업 round 증가
- 기본 3-pane과 선택형 3-window 화면
- 사용자 확인을 위한 `Ctrl+b Enter` 또는 `atcode next`

자유 역할 편집, 범용 Task Queue, Workflow DSL, 자동 Agent 대화, Database,
Web UI, 전체 대화 이력 저장, 자동 병렬 Team은 실제 필요가 확인될 때까지 추가하지
않습니다.

## 제거

명령만 제거하고 Runtime 데이터는 보존합니다.

```bash
./scripts/uninstall.sh
```

Runtime 데이터까지 제거하려면 정확한 삭제 경로를 확인한 뒤 `DELETE`를 입력해야 합니다.

```bash
./scripts/uninstall.sh --purge-data
```

## 개발 검증

AtCode 저장소를 수정한 뒤에는 WSL에서 개발용 가상환경을 활성화하고 다음 검증을
실행합니다. 일반 사용자에게는 이 과정이 필요하지 않습니다.

```bash
cd /mnt/d/myproject/AtCode
source "$HOME/.venvs/atcode/bin/activate"
python -m pytest -q
python -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

## 실제 동작 테스트

실제 tmux와 Codex 연동은 WSL의 별도 테스트 프로젝트에서 확인합니다. 테스트
프로젝트는 실제 업무 프로젝트와 분리해서 만드는 것을 권장합니다.

```bash
mkdir -p "$HOME/atcode-test/plain-project"
cd "$HOME/atcode-test/plain-project"

atcode init
atcode doctor
atcode start
atcode status
atcode attach
```

attach한 뒤 다음 순서로 확인합니다.

1. 세 pane에 PM, Developer, Reviewer가 모두 실행되어 있는지 확인합니다.
2. PM에게 테스트용 작업을 지시하고 응답 마지막에 handoff 블록이 생성되는지 확인합니다.
3. `Ctrl+b Enter`를 눌러 Developer로 전달되고 선택 pane도 이동하는지 확인합니다.
4. Developer 응답이 끝나면 다시 `Ctrl+b Enter`를 눌러 Reviewer로 전달되는지 확인합니다.
5. Reviewer가 승인하면 PM으로 돌아오며 workflow가 완료 상태가 되는지 확인합니다.
6. `Ctrl+b d`로 빠져나온 뒤 `atcode status`에서 현재 역할, round, 최근 전달 상태를 확인합니다.
7. `atcode stop`과 `atcode start`를 차례로 실행한 뒤 최신 handoff가 복원되는지 확인합니다.

여러 프로젝트 세션도 함께 확인하려면 서로 다른 두 WSL 터미널에서 각각 다른
테스트 프로젝트를 `init`, `start`, `attach`한 뒤 `atcode list`에 두 프로젝트가
모두 실행 중으로 표시되는지 확인합니다.

테스트가 끝나면 각 테스트 프로젝트에서 세션을 종료합니다.

```bash
atcode stop --project "$HOME/atcode-test/plain-project"
```

AtCode의 설정, Prompt, workflow 상태는 작업 대상 프로젝트가 아니라
`ATCODE_HOME` 아래에 생성되어야 합니다. 대상 프로젝트에 `.atcode`, Runtime
Workspace, 로그 같은 AtCode 관리 파일이 생기지 않았는지도 함께 확인합니다.

상세 설계는 다음 문서에서 확인할 수 있습니다.

- `docs/superpowers/specs/2026-07-15-atcode-phase1-design.md`
- `docs/superpowers/specs/2026-07-15-three-role-runtime-design.md`
- `docs/superpowers/specs/2026-07-15-guided-wsl-installer-design.md`
- `docs/superpowers/specs/2026-07-15-phase2-relay-workflow-design.md`
