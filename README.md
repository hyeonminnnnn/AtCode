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

```bash
cd /path/to/AtCode
./scripts/install.sh
```

`~/.local/bin`이 `PATH`에 없다면 셸 설정에 추가한다.

```bash
export PATH="$HOME/.local/bin:$PATH"
```

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

Phase 1의 역할은 다음 5개로 고정된다.

```text
pm
developer
reviewer
tester
docs
```

기본 Adapter 배정:

```text
pm        = codex
developer = codex
reviewer  = codex
tester    = codex
docs      = codex
```

현재 기본값은 다섯 역할 모두 Codex다. Claude, Gemini, Shell Adapter 지원은
유지되므로 필요한 CLI가 설치되어 있다면 역할별 설정으로 변경할 수 있다.

각 역할 Prompt에는 특정 AI 모델의 스킬 이름이나 호출 문법 대신 요구사항 명세,
점진적 구현, 테스트 우선 개발, 품질·과설계 검토, 증거 중심 테스트, 문서화와
한국어 윤문 절차가 자연어로 포함된다. 따라서 다른 Adapter를 선택해도 같은 역할
Prompt를 사용할 수 있다.

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

상세 설계는 `docs/superpowers/specs/2026-07-15-atcode-phase1-design.md`에서 확인할 수 있다.
