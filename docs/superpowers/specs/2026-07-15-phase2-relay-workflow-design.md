# Spec: Phase 2 Relay Workflow

## 가정

1. Phase 2의 고정 역할은 `pm`, `developer`, `reviewer` 세 개다.
2. 프로젝트당 동시에 진행하는 Workflow는 하나뿐이다.
3. 사용자는 PM에게 요구사항을 전달하고, 이후 기본적으로 `Ctrl+b Enter`만 눌러 다음 역할로 진행한다.
4. `/next`는 Runtime의 제어 개념으로 유지하되 AI CLI 입력창의 Slash Command로 구현하지 않는다.
5. Runtime의 공개 대체 명령은 `atcode next`다.
6. 기본 화면은 하나의 `team` Window에 세 역할 Pane을 동시에 보여 주는 형태다.
7. 기존 세 Window 방식은 설정으로 유지하지만 실행 중인 Session의 Layout을 실시간 변환하지는 않는다.
8. 역할 Prompt와 최신 인계는 서로 다른 파일에 저장하며 Prompt 파일에 작업 내용을 누적하지 않는다.
9. tmux 화면에서 구조화된 인계 영역을 찾기 위해 Phase 2부터 `capture-pane`을 사용하고, 다음 역할에 전달하기 위해 tmux Buffer와 입력 전달 기능을 사용한다.
10. 전체 대화는 저장하지 않고 가장 최근의 유효한 인계 하나만 보존한다.

## Objective

사용자가 AI 역할 사이에서 내용을 복사하지 않아도 다음 한 가지 개발 루프를 반복할 수 있게 한다.

```text
PM → Developer → Reviewer → PM
```

성공한 Phase 2에서는 다음이 가능하다.

- PM, Developer, Reviewer를 한 화면의 세 Pane으로 동시에 본다.
- 현재 역할의 작업이 끝나면 `Ctrl+b Enter`로 구조화된 인계만 다음 역할에 전달한다.
- Reviewer의 승인과 반려에 따라 완료 또는 재작업 상태를 구분한다.
- 컴퓨터나 WSL을 다시 시작해도 현재 역할과 최신 인계를 복구한다.
- 모든 상태와 인계는 `ATCODE_HOME`에만 저장한다.

## 검토한 조작 방식

### A. `atcode next`와 tmux 단축키 결합 — 채택

Runtime은 테스트 가능한 `atcode next` 명령을 제공하고 Tmux Backend는 `Ctrl+b Enter`를 이 명령에 연결한다.

- 장점: 사용자는 단축키 한 번만 누르면 된다.
- 장점: Workflow 로직이 tmux 명령과 분리된다.
- 장점: 향후 Backend는 각 Terminal에 맞는 조작만 새로 구현할 수 있다.
- 장점: 단축키를 사용할 수 없을 때 `atcode next`가 복구 경로가 된다.
- 단점: tmux Server의 기존 Key Binding과 충돌하는지 확인해야 한다.

### B. AI CLI 입력창의 `/next` — 제외

Codex, Claude, Gemini가 Slash Command를 서로 다르게 처리한다. Runtime이 입력을 가로채려면 AI CLI를 감싸는 PTY Wrapper가 필요해져 Phase 2의 핵심보다 구현 범위가 커진다.

### C. Shell에서만 `atcode next` 실행 — 대체 경로로만 유지

구현과 테스트는 단순하지만 사용자가 tmux를 빠져나가 별도 Shell에서 명령을 실행해야 하므로 기본 UX로 사용하지 않는다.

## 사용자 경험

### 기본 실행

```bash
cd /path/to/project
atcode start
atcode attach
```

기본 Layout은 다음과 같다.

```text
team
├─ pane: pm
├─ pane: developer
└─ pane: reviewer
```

각 Pane에는 위치나 크기와 무관한 `Role` Metadata를 지정한다. 현재 Pane이 PM이면 `Ctrl+b Enter`는 Developer로, Developer면 Reviewer로, Reviewer면 PM으로 전달한다. 전달에 성공하면 대상 Pane을 활성화한다.

선택한 Pane만 크게 보는 기능은 tmux 기본 명령인 `Ctrl+b z`를 사용한다.

### 세 Window Layout

기존 방식이 필요한 사용자는 다음 설정을 사용할 수 있다.

```bash
atcode config set layout windows
atcode stop
atcode start
```

기본값으로 돌아갈 때는 다음을 사용한다.

```bash
atcode config set layout panes
atcode stop
atcode start
```

Layout은 `panes` 또는 `windows`만 허용한다. 실행 중인 Process를 `join-pane`과 `break-pane`으로 실시간 이동하는 기능은 Phase 2에서 구현하지 않는다.

### 단축키 대체 명령

단축키를 사용할 수 없는 경우 프로젝트 Root에서 다음 명령을 실행한다.

```bash
atcode next
```

Tmux Backend가 단축키를 호출할 때는 현재 Session과 Pane 식별자를 내부 인자로 전달한다. 일반 사용자는 이 내부 인자를 입력하지 않는다.

## 역할 Prompt와 시작 Prompt

원본 역할 Template은 AtCode 저장소의 `prompts/`에 둔다. Runtime은 프로젝트 정보를 적용해 다음 위치에 프로젝트별 역할 Prompt를 생성한다.

```text
ATCODE_HOME/projects/<project-id>/workspace/prompts/
├─ pm.md
├─ developer.md
└─ reviewer.md
```

이 파일은 역할과 작업 방식의 계약이며 인계 내용을 추가하지 않는다. 매 `atcode start`에서 Template을 다시 Render한다.

AI CLI가 역할 파일을 직접 읽게 하지 않는다. Runtime이 역할 Prompt와 필요한 재개 인계를 읽어 메모리에서 시작 Prompt를 조합하고, Adapter가 각 AI CLI의 공식 초기 Prompt 방식으로 전달한다. 이렇게 하면 파일 읽기 도구와 권한에 의존하지 않고 Adapter마다 다른 파일 참조 문법도 Runtime 밖으로 격리할 수 있다.

`StartupPromptBuilder`는 역할 계약과 별도로 `active` 또는 `waiting` 실행 모드를 추가한다.

- 현재 Workflow 역할은 `active`이며 사용자 요구나 전달받은 Handoff를 처리한다.
- 나머지 두 역할은 `waiting`이며 새 Handoff를 받기 전에는 프로젝트 조사, 파일 변경, 검토를 시작하지 않는다.
- 대기 응답에는 `<ATCODE_HANDOFF>`를 만들지 않는다.

최초 `idle` 상태에서는 PM만 `active`이고 Developer와 Reviewer는 `waiting`이다. 재부팅 복구에서는 `workflow.json`의 현재 역할만 `active`로 시작한다. 이렇게 해야 세 AI Process가 역할 Prompt를 받자마자 동시에 불필요한 작업을 시작하지 않는다.

실행 중인 tmux Session이 살아 있으면 `atcode attach`는 기존 Process에 연결하므로 Prompt를 다시 전달하지 않는다. Session이 없어서 새 Process를 만들 때만 시작 Prompt를 전달한다.

## 구조화된 인계 계약

각 역할 Prompt는 작업 결과의 마지막에 다음 영역을 하나 출력하도록 요구한다.

```text
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
다음 역할이 알아야 할 내용
</ATCODE_HANDOFF>
```

Runtime은 가장 최근의 완성된 `<ATCODE_HANDOFF>` 영역 하나만 사용한다. 영역 밖의 대화, 도구 출력, 진행 로그는 저장하거나 전달하지 않는다.

허용하는 `STATUS`는 역할별로 제한한다.

```text
PM         ready
Developer  ready
Reviewer   approved | rejected
```

`SUMMARY`는 비어 있을 수 없고 UTF-8 기준 최대 32 KiB로 제한한다. Runtime은 Protocol Marker, Status, 크기만 검증한다. 역할별로 필요한 요구사항, 완료 조건, 변경 파일, 테스트 증거, 반려 사유의 내용은 역할 Prompt가 규정한다.

각 인계는 다음 역할이 이전 대화를 보지 않아도 이해할 수 있는 자기완결형 요약이어야 한다.

## Workflow 상태 전이

Workflow의 상태는 `idle`, `active`, `rework`, `complete` 네 개만 사용한다.

| 현재 상태 | 현재 역할 | 인계 상태 | 다음 상태 | 다음 역할 | Round |
|---|---|---|---|---|---|
| `idle` | PM | `ready` | `active` | Developer | 1 |
| `active` | Developer | `ready` | `active` | Reviewer | 유지 |
| `active` | Reviewer | `approved` | `complete` | PM | 유지 |
| `active` | Reviewer | `rejected` | `rework` | PM | 유지 |
| `rework` | PM | `ready` | `active` | Developer | 1 증가 |
| `complete` | PM | `ready` | `active` | Developer | 1로 초기화 |

Workflow가 없으면 `idle`, 현재 역할 PM으로 간주한다. 현재 역할과 실제로 단축키를 누른 Pane의 역할이 다르면 전달하지 않는다. Shell의 `atcode next`는 `workflow.json`의 현재 역할을 사용한다.

Reviewer가 승인한 결과를 PM에게 전달하는 순간 Workflow는 `complete`가 된다. PM은 최종 요약을 사용자에게 제공하며 추가 전달을 누르지 않는다. 이후 PM이 새 작업을 인계하면 같은 프로젝트의 새 Cycle을 시작한다.

## Runtime Workspace

Phase 2는 다음 파일만 추가한다.

```text
ATCODE_HOME/projects/<project-id>/workspace/
├─ prompts/
│  ├─ pm.md
│  ├─ developer.md
│  └─ reviewer.md
├─ workflow.json
└─ handoff.json
```

`workflow.json`은 현재 상태만 저장한다.

```json
{
  "schemaVersion": 1,
  "status": "active",
  "currentRole": "developer",
  "round": 1,
  "lastTransferId": 1,
  "lastDigests": {
    "pm": "sha256:..."
  },
  "updatedAt": "2026-07-15T00:00:00+00:00"
}
```

`handoff.json`은 최신 인계 하나만 저장하고 다음 전달에서 교체한다.

```json
{
  "schemaVersion": 1,
  "transferId": 1,
  "fromRole": "pm",
  "toRole": "developer",
  "decision": "ready",
  "delivery": "delivered",
  "digest": "sha256:...",
  "body": "다음 역할이 알아야 할 내용",
  "createdAt": "2026-07-15T00:00:00+00:00",
  "deliveredAt": "2026-07-15T00:00:01+00:00"
}
```

`delivery`는 `pending` 또는 `delivered`만 허용한다. 두 JSON 파일은 기존 Runtime Store와 같은 Lock 및 Atomic Replace 방식으로 기록한다. 전체 인계 이력, 로그, 대화 Transcript는 만들지 않는다.

## `next` 처리 흐름

`WorkflowService.next()`는 다음 순서를 따른다.

1. 프로젝트 Runtime Lock을 획득한다.
2. Session과 세 Role Endpoint가 정상인지 확인한다.
3. 현재 Workflow 역할과 요청한 Source Pane 역할이 일치하는지 확인한다.
4. Backend에서 Source 역할의 출력 내용을 일시적으로 읽는다.
5. 가장 최근의 완성된 인계 영역을 추출하고 Status, 본문, 크기를 검증한다.
6. 역할별 마지막 Digest와 비교해 이미 전달한 인계가 아닌지 확인한다.
7. 새 Transfer ID로 `handoff.json`을 `pending` 상태로 기록한다.
8. Backend를 통해 Transfer Envelope와 본문을 Target 역할에 전달한다.
9. 전달 성공 후 `handoff.json`을 `delivered`로 기록하고 `workflow.json`을 다음 상태로 전이한다.
10. Target 역할을 활성화한다. Focus 실패는 전달 성공을 되돌리지 않고 경고로 보고한다.

전달 Envelope에는 중복 감지를 위한 Transfer ID가 포함된다.

```text
[ATCODE_TRANSFER id=1 from=pm to=developer]
...
```

Terminal에 텍스트를 전달했다는 사실과 AI가 작업을 완료했다는 사실은 다르다. Phase 2는 AI의 수신 확인 Protocol을 구현하지 않으며 Backend 명령이 성공하면 전달 성공으로 판단한다.

## 실패와 재시도

다음 경우에는 상태를 전이하지 않는다.

- Session 또는 역할 Endpoint가 없음
- 현재 Workflow 역할과 Source Pane 역할이 다름
- 완성된 인계 영역이 없음
- Status가 Source 역할에서 허용되지 않음
- 본문이 비었거나 32 KiB를 초과함
- 이전에 전달한 것과 같은 Digest임
- Target 역할에 전달하지 못함

전달 전에 실패하면 `handoff.json`을 변경하지 않는다. 전달 단계에서 실패하면 `pending` 인계를 보존한다. 다음 `atcode next`는 화면을 다시 캡처하지 않고 동일한 Pending Transfer를 먼저 재시도한다.

Backend 전달 직후 Process가 중단되면 같은 Transfer가 한 번 더 전달될 가능성이 있다. Phase 2의 보장 수준은 Exactly Once가 아니라 At Least Once다. 동일한 Transfer ID가 다시 보이면 역할 Prompt는 이미 처리한 ID를 중복 작업하지 않도록 요구한다.

`handoff.json`이 `delivered`인데 `workflow.json.lastTransferId`가 더 작으면 전달 성공 후 Workflow 저장 전에 Process가 중단된 상태다. 다음 `start`, `status`, `doctor`는 Handoff의 `toRole`, `decision`, `transferId`를 사용해 동일한 상태 전이를 한 번 적용하고 Workflow를 복구한다. 반대로 Handoff가 `pending`이면 전달 성공을 추측하지 않고 Source 역할에 머문다.

## 재부팅과 복구

컴퓨터 종료나 WSL 중지로 tmux Session이 사라져도 `workflow.json`과 `handoff.json`은 남는다.

다음 `atcode start`는 역할 Prompt를 다시 Render하고 새 AI CLI Process를 실행한다.

- `idle`: PM에는 역할 Prompt만 전달한다.
- `active`: 현재 Developer 또는 Reviewer에게 역할 Prompt와 최신 Delivered Handoff를 함께 전달한다.
- `rework`: PM에게 역할 Prompt와 Reviewer의 반려 Handoff를 함께 전달한다.
- `complete`: PM에게 역할 Prompt와 Reviewer의 승인 Handoff를 함께 전달한다.
- `pending`: Source 역할을 현재 역할로 유지하고 자동 전달하지 않으며 재시도 안내를 표시한다.

시작 Prompt를 조합하기 전에 Delivered Handoff와 Workflow의 Transfer ID를 대조해 위 복구 규칙을 적용한다.

재개 내용은 메모리에서 시작 Prompt에 조합한다. 역할 Prompt 파일 자체는 수정하지 않는다.

오래된 Workflow를 폐기해야 할 때만 다음 명령을 사용한다.

```bash
atcode start --fresh
```

`--fresh`는 정확한 프로젝트 ID와 현재 상태를 보여 주고 확인을 받은 뒤 `workflow.json`을 `idle`로 재설정하고 `handoff.json`을 제거한다. 정상적인 재부팅 복구에는 사용하지 않는다.

## Runtime, Backend, Adapter 경계

### Domain과 Application

- `WorkflowState`: 현재 상태, 역할, Round, 마지막 Transfer 정보
- `Handoff`: 최신 인계 값 객체
- `HandoffParser`: Marker와 Protocol Field 검증
- `WorkflowService`: 상태 전이, 저장, Backend 호출 순서
- `StartupPromptBuilder`: 역할 Prompt와 현재 역할의 재개 인계를 메모리에서 조합

### Terminal Backend Port

Terminal Backend는 Session Lifecycle 외에 다음 논리 기능을 제공한다.

```text
inspect role endpoints
read role output
deliver text to role
focus role
install next action
```

Application Layer는 `capture-pane`, `paste-buffer`, `select-pane`, Window 이름을 알지 않는다.

### Tmux Backend

Tmux Backend는 다음을 담당한다.

- `panes` Layout에서 `team` Window와 세 Pane 생성
- `windows` Layout에서 세 역할 Window 생성
- 각 Pane에 AtCode Role Metadata 지정
- `team` Window의 Pane Border에 PM, Developer, Reviewer 이름 표시
- 역할 출력의 일시적 `capture-pane`
- 인계 파일을 tmux Buffer에 Load하고 Target Pane에 Paste
- 제출에 필요한 Enter Key 전달
- Target Pane 또는 Window 선택
- `Ctrl+b Enter`와 `atcode next` 연결

인계 본문을 Shell Command 문자열에 삽입하지 않는다. `ATCODE_HOME`의 안전한 Transfer 파일을 tmux Buffer로 Load해 특수문자와 줄바꿈이 Shell 명령으로 해석되지 않게 한다.

### Adapter

Adapter는 AI CLI Probe와 초기 실행 명령만 담당한다. Workflow Routing, tmux Capture, Handoff 저장을 알지 않는다. Codex, Claude, Gemini, Shell Adapter의 기존 경계를 유지한다.

## tmux 단축키 정책

AtCode는 `.tmux.conf`를 수정하지 않는다. 실행 중인 tmux Server에만 AtCode 소유 Binding을 등록한다.

- `Ctrl+b Enter`가 비어 있거나 이미 AtCode Binding이면 사용한다.
- 다른 Binding이 있으면 덮어쓰지 않는다.
- 충돌은 `atcode doctor`와 `atcode start`에서 경고한다.
- 충돌 시 `atcode next`를 대체 명령으로 안내한다.
- AtCode Session이 아닌 tmux Session에서는 AtCode Binding이 상태를 변경하지 않는다.
- 단축키로 실행한 `next`의 성공 또는 오류는 tmux `display-message`로 현재 화면에 표시한다.

## 기존 데이터와 호환

Configuration schema version 1에 선택적 `layout`을 추가한다. 값이 없으면 Phase 2 기본값인 `panes`를 사용한다.

Phase 1 Runtime State는 세 역할 Window를 전제로 한다. Phase 2 State는 Backend의 휘발성 Pane ID를 저장하지 않고 논리 Role Endpoint와 Layout만 저장한다. State schema version 2를 사용하며 schema version 1의 Role Window는 `windows` Layout의 논리 Endpoint로 읽는다. 다음 State 저장에서 version 2로 기록한다.

실행 중인 Phase 1 세 Window Session은 Phase 2 기본 `panes` Layout과 다르므로 자동 재배치하지 않는다. 다음 순서로 전환한다.

```bash
atcode stop
atcode start
atcode attach
```

기존 프로젝트 등록, Adapter 설정, Rendered Prompt는 유지한다.

## Commands

Phase 2에서 추가하거나 확장하는 사용자 명령은 다음뿐이다.

```bash
atcode next
atcode start --fresh
atcode config set layout panes
atcode config set layout windows
```

기존 명령은 유지한다.

```bash
atcode init
atcode start
atcode attach
atcode stop
atcode status
atcode doctor
atcode config
atcode list
```

`atcode status`는 Session 상태와 함께 Workflow 상태, 현재 역할, Round, 최신 Transfer ID와 Delivery 상태를 표시한다. `atcode doctor`는 Layout 지원, 세 Role Endpoint, 단축키 충돌, Workflow와 Handoff JSON의 일관성을 진단한다.

## 예상 Project Structure

```text
src/atcode/domain/models.py
  Workflow, Handoff, Role Endpoint 값 객체
src/atcode/ports/backend.py
  역할 출력, 전달, Focus, Next Action 계약
src/atcode/ports/storage.py
  Workflow와 Handoff Store 계약
src/atcode/application/workflow.py
  next 상태 전이와 재시도
src/atcode/application/handoffs.py
  구조화된 인계 Parsing과 검증
src/atcode/application/prompts.py
  역할 Prompt와 재개 인계의 시작 Prompt 조합
src/atcode/infrastructure/tmux_backend.py
  Pane Layout, Capture, Buffer Paste, Focus, Binding
src/atcode/infrastructure/storage/workflow.py
  workflow.json과 handoff.json Atomic Store
src/atcode/cli.py
  next, start --fresh, 상태 출력
prompts/*.md
  역할별 Handoff 출력 계약과 중복 Transfer 처리 규칙
tests/unit, tests/integration
  Parser, 상태 전이, 저장, Backend 명령, CLI, 무흔적 검증
```

구현 계획에서 SRP를 해치지 않는 범위로 파일을 더 작게 합치거나 나눌 수 있지만 Domain, Application, Backend, Adapter 경계는 유지한다.

## Testing Strategy

### Unit

1. 최신 완성 Handoff만 추출한다.
2. Marker 누락, 잘못된 Status, 빈 본문, 크기 초과를 거부한다.
3. PM, Developer, Reviewer의 허용 Status를 구분한다.
4. 모든 정상 Workflow 상태 전이를 검증한다.
5. 현재 역할이 아닌 Source 전달과 같은 Digest 재전달을 거부한다.
6. Pending Transfer는 새 Capture보다 우선 재시도한다.
7. Prompt 파일을 수정하지 않고 현재 역할에만 재개 Handoff를 조합한다.
8. Workflow와 Handoff JSON을 Atomic하게 읽고 쓰며 손상된 입력을 거부한다.
9. schema version 1 Runtime State를 windows Layout의 version 2 State로 읽는다.

### Tmux Backend

1. 기본 Session이 `team` Window와 세 Role Pane을 만든다.
2. windows 설정은 기존 세 Window를 만든다.
3. Role Metadata로 Layout과 무관하게 Endpoint를 찾는다.
4. Source 출력 Capture, Buffer Load, Paste, Enter, Focus 명령을 올바른 Target에 실행한다.
5. 인계 본문의 따옴표, 줄바꿈, `$()`, Backtick이 Shell로 실행되지 않는다.
6. 기존 `Ctrl+b Enter` Binding을 덮어쓰지 않는다.
7. 일부 Pane이 없으면 Degraded 상태를 반환한다.

### Integration

1. `atcode next`가 PM → Developer → Reviewer → PM 순서로 전달한다.
2. Reviewer approved와 rejected가 complete와 rework로 분기한다.
3. 전달 실패 시 Workflow는 전이되지 않고 Pending Handoff가 재시도된다.
4. Session 재생성 시 현재 역할에 최신 Delivered Handoff가 복구된다.
5. `--fresh`는 확인 없이는 Workflow를 초기화하지 않는다.
6. status와 doctor가 Workflow와 단축키 상태를 설명한다.
7. Phase 1 설정과 State를 읽을 수 있다.
8. 모든 명령 전후 대상 프로젝트의 파일 목록이 동일하다.

### WSL 인수 검증

1. 실제 Codex 세 Process가 3-Pane으로 실행된다.
2. 각 역할이 Handoff 영역을 출력하고 `Ctrl+b Enter`로 다음 Pane에 전달된다.
3. `Ctrl+b z`로 선택 Pane을 확대하고 다시 3-Pane으로 복귀할 수 있다.
4. tmux Session 종료 후 `atcode start`가 현재 역할과 최신 인계를 복구한다.
5. windows Layout에서도 같은 단축키와 Workflow가 동작한다.

개발 검증 명령은 Phase 1과 동일하게 유지한다.

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

## Boundaries

### Always

- Runtime 데이터는 `ATCODE_HOME`에만 기록한다.
- 인계 전에 구조, 역할, Status, 크기, Digest를 검증한다.
- Backend 오류가 있으면 Workflow 상태를 앞서 진행하지 않는다.
- Prompt와 최신 Handoff의 저장 책임을 분리한다.
- Backend에 전달하는 본문을 Shell Command로 조합하지 않는다.
- 기존 Phase 1 설정과 상태의 마이그레이션을 테스트한다.

### Ask first

- 고정 역할 추가, 삭제, 이름 변경
- 전체 대화 또는 전체 인계 이력 저장
- 단축키 기본값 변경
- AI CLI Session의 Native Resume 기능 사용
- 임시 병렬 Developer Team 구현
- Workflow JSON schema version 변경

### Never

- 대상 프로젝트에 AtCode 설정, 상태, Prompt, Handoff, Log, Workspace를 만든다.
- 사용자 tmux 설정 파일을 수정한다.
- 기존 tmux Key Binding을 조용히 덮어쓴다.
- Capture한 전체 Pane 내용을 저장한다.
- Marker가 없거나 잘못된 출력을 임의로 다음 역할에 전달한다.
- Phase 2에 범용 Task Queue, Workflow DSL, Database, Web UI를 추가한다.

## 구현하지 않는 것

- 자유 역할 편집
- 여러 활성 작업 또는 Task Queue
- 전체 대화 저장과 검색
- 범용 자동 Agent 대화
- Background Worker 또는 Daemon
- Database
- Web UI
- 실행 중 Layout 실시간 변환
- 승인 기반 임시 Developer Team
- AI가 전달을 처리했다는 수신 확인 Protocol

병렬 Team은 단일 Relay Loop가 실제 사용에서 검증된 뒤 별도 설계한다.

## Success Criteria

1. 기본 `atcode start`가 하나의 `team` Window에 PM, Developer, Reviewer 세 Pane을 만든다.
2. 사용자가 현재 역할 Pane에서 `Ctrl+b Enter`를 누르면 유효한 최신 Handoff만 정확한 다음 역할에 전달된다.
3. 전달 성공 후 Target Pane이 활성화되고 Workflow 상태가 한 단계 진행된다.
4. Reviewer 승인과 반려가 complete와 rework로 정확히 구분된다.
5. Session 재생성 후 현재 역할과 최신 Delivered Handoff를 복구한다.
6. Prompt 파일에는 역할 계약만 있고 인계 내용이 누적되지 않는다.
7. 최신 Handoff 하나만 `handoff.json`에 남는다.
8. 단축키 충돌, 잘못된 Handoff, Backend 실패가 기존 상태나 사용자 tmux 설정을 손상시키지 않는다.
9. panes와 windows Layout이 같은 Workflow Service를 사용한다.
10. 대상 프로젝트에는 AtCode 관리 흔적이 전혀 생기지 않는다.
11. Phase 1 호환 테스트와 전체 자동 검증이 통과한다.

## Open Questions

없음. 기본 Layout, 사용자 조작, Handoff 형식, 저장 범위, 재부팅 복구, 실패 처리와 Phase 2 경계는 승인된 상태다.
