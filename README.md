# AtCode

AtCode는 Codex, Claude, Gemini 같은 AI CLI를 역할 기반 개발팀으로 실행하는 Runtime이다. Phase 1은 WSL2와 Linux에서 tmux를 Backend로 사용한다.

## 핵심 원칙

- AtCode 설정, 상태, Prompt, Workspace는 `ATCODE_HOME`에만 저장한다.
- 실제 작업 대상 프로젝트에는 AtCode 관리 파일을 만들지 않는다.
- AI CLI는 사용자가 지시한 개발 작업에 따라 대상 프로젝트 소스를 수정할 수 있다.
- Phase 1은 Agent 자동 전달, Task Queue, `send-keys`, `capture-pane`를 지원하지 않는다.

## 요구 환경

- Python 3.11 이상
- WSL2 또는 Linux
- tmux
- 역할에 배정할 Codex, Claude, Gemini CLI 중 필요한 명령

## 설치

WSL에서 AtCode 저장소로 이동해 안내형 설치기를 실행한다.

```bash
cd /mnt/d/myproject/AtCode
bash scripts/install.sh
```

설치기는 Python, tmux, WSL/Linux용 Codex, PATH, 로그인 상태를 순서대로
확인한다. 시스템 패키지 설치, 공식 Codex 설치, `.bashrc` 수정, 로그인은 실행
전에 동의를 구한다. 마지막에는 `atcode doctor`를 자동 실행한다.

화면에 `source "$HOME/.bashrc"`가 표시되면 한 번 실행해 현재 터미널에 PATH를
적용한다. 일반 사용에는 Python 가상환경, pip, pytest가 필요하지 않다.

개발 단계의 기본 Runtime 위치는 AtCode 저장소의 `data/`다. 다른 위치를 사용하려면 절대 경로를 지정한다.

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

tmux에서 detach한 뒤 상태 확인과 종료:

```bash
atcode status
atcode stop
```

다른 위치에서 프로젝트를 명시할 수도 있다.

```bash
atcode status --project /mnt/d/project/SmileLRS
```

## 역할과 Adapter

Phase 1은 다음 세 역할의 단일 Workflow를 사용한다.

```text
PM → Developer → Reviewer → PM
```

역할 책임:

```text
PM         요구사항 분석, 완료 조건, 작업 배분, 결과 확인, 최종 정리
Developer  프로젝트에 필요한 프론트엔드·백엔드·디자인·문서 구현
Reviewer   코드 리뷰, 과설계 점검, 테스트 실행과 최종 검증
```

Developer는 고정된 Frontend·Backend 역할로 나뉘지 않는다. 프로젝트와 PM Brief를
읽고 필요한 전문 영역을 판단한다. 병렬 작업이 실제로 필요하면 향후 Developer가
독립 작업과 통합 순서를 제안하고, PM 또는 사용자 승인 후에만 임시 Team을 만드는
방향으로 확장한다.

세 역할의 기본 Adapter는 모두 Codex다. Claude, Gemini, Shell Adapter 지원은
유지되므로 필요한 CLI가 설치되어 있다면 역할별로 변경할 수 있다.

각 역할 Prompt에는 특정 AI 모델의 스킬 이름이나 호출 문법 대신 요구사항 명세,
점진적 구현, 테스트 우선 개발, 품질·과설계 검토, 증거 중심 테스트, 문서화와
한국어 윤문 절차가 자연어로 포함된다. 따라서 다른 Adapter를 선택해도 같은 역할
Prompt를 사용할 수 있다.

기존 5역할 세션은 다음 순서로 세 역할 세션으로 전환한다. 기존 tmux 대화 내용은
세션 종료와 함께 사라진다.

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

전역 기본값 변경:

```bash
atcode config set roles.developer.adapter codex --global
```

Adapter는 각 CLI의 공식 대화형 최초 Prompt 규약을 사용한다.

- [Codex CLI 명령 참고](https://developers.openai.com/codex/cli/reference/)
- [Claude Code CLI 참고](https://code.claude.com/docs/en/cli-usage)
- [Gemini CLI 참고](https://geminicli.com/docs/cli/cli-reference/)

## 명령

```text
atcode init
atcode start
atcode attach
atcode stop
atcode status
atcode doctor
atcode config
atcode list
```

## Phase 2 방향

Phase 2는 기능을 넓히기보다 다음 한 가지 개발 루프를 먼저 완성한다.

```text
PM /next → Developer /next → Reviewer /next → PM
```

- 프로젝트당 활성 작업 하나
- `/next`를 통한 역할 결과 전달
- 선택적인 3-pane 동시 보기
- 병렬 이득이 확인된 경우에만 승인 기반 임시 Developer Team

자유 역할 편집, 범용 Task Queue, Workflow DSL, 자동 Agent 대화, Database,
Web UI는 실제 필요가 확인될 때까지 추가하지 않는다.

## 제거

명령만 제거하고 Runtime 데이터는 보존한다.

```bash
./scripts/uninstall.sh
```

Runtime 데이터까지 제거하려면 정확한 삭제 경로를 확인한 뒤 `DELETE`를 입력해야 한다.

```bash
./scripts/uninstall.sh --purge-data
```

## 개발 검증

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

상세 설계는 다음 문서에서 확인할 수 있다.

- `docs/superpowers/specs/2026-07-15-atcode-phase1-design.md`
- `docs/superpowers/specs/2026-07-15-three-role-runtime-design.md`
- `docs/superpowers/specs/2026-07-15-guided-wsl-installer-design.md`
