# Spec: Phase 1 세 역할 Runtime

## 가정

1. Phase 1의 고정 역할은 `pm`, `developer`, `reviewer` 세 개다.
2. Tester의 테스트 실행과 검증 책임은 Reviewer가 맡는다.
3. Docs의 결과 정리와 자연스러운 한국어 작성 책임은 PM이 맡는다.
4. 실제 프로젝트 문서 파일 변경이 구현 범위에 포함되면 Developer가 수행하고 Reviewer가 검증한다. PM은 사용자에게 전달할 최종 정리를 담당한다.
5. 기존 5역할 설정과 상태를 가진 사용자는 수동으로 Runtime 파일을 편집하지 않아도 된다.
6. Phase 2 제어 명령의 정식 표기는 일반 대화와 구분되는 `/next`다. Phase 1에는 역할 간 메시지 전달을 추가하지 않는다.

## Objective

Phase 1 Runtime을 다음 세 역할로 단순화한다.

```text
PM → Developer → Reviewer → PM
```

역할 수를 줄이되 기존 Tester와 Docs가 제공하던 필수 검증 및 정리 책임은 잃지 않는다. 새 프로젝트는 세 개의 tmux Window만 생성하고, 기존 5역할 Runtime 데이터는 안전하게 읽어 세 역할 구조로 전환한다.

## 검토한 접근

### A. 세 역할로 완전히 축소 — 채택

Domain Role, 기본 설정, Prompt, tmux Window, 상태에서 Tester와 Docs를 제거한다.

- 장점: 사용자에게 보이는 팀 구조와 내부 구조가 일치한다.
- 장점: Codex 프로세스와 tmux Window가 다섯 개에서 세 개로 줄어든다.
- 장점: Phase 2 Workflow와 Relay의 상태 전이가 단순해진다.
- 단점: 기존 설정과 상태를 읽는 호환 처리가 필요하다.

### B. 세 역할만 표시하고 내부 역할 유지 — 제외

Tester와 Docs를 숨긴 채 Domain과 상태에는 남겨 둔다. 표시와 내부 상태가 달라져 진단과 Phase 2 Workflow가 복잡해진다.

### C. 다섯 역할을 선택적으로 활성화 — 제외

역할 활성화 설정을 새로 추가해야 하며, 사용자 정의 역할을 다룰 Phase 2보다 먼저 불완전한 역할 관리 기능을 만들게 된다.

## 역할 계약

### PM

PM은 지휘와 최종 정리를 담당한다.

- 요구사항 분석, 가정 공개, 범위와 완료 조건 정의
- 작업 분할과 Developer 전달용 Brief 작성
- Developer와 Reviewer 결과를 완료 조건과 대조
- 결함이 있으면 담당과 재검증 조건이 포함된 재작업 지시 작성
- 구현 및 검증 근거에 맞는 최종 요약 작성
- 명령, 경로, 설정 키, 제한사항을 실제 결과와 대조
- 한국어 최종 문장의 번역투, 기계적 반복, 불필요한 접속사를 줄이되 기술적 의미는 보존

PM은 별도 Docs 역할처럼 무조건 프로젝트 문서를 수정하지 않는다. 프로젝트 문서 변경이 사용자 요구에 포함되면 이를 Developer 작업으로 명세하고 Reviewer 검증 항목으로 포함한다.

### Developer

Developer는 승인된 명세에 따른 구현을 담당한다.

- 작은 단위로 구현하고 관련 테스트를 함께 작성
- 프로젝트의 기존 코드 스타일과 도구를 우선 사용
- 실제 변경 파일과 실행한 검증 명령을 보고
- 프로젝트 문서 변경이 명세에 포함되면 구현과 함께 반영
- 범위 밖 문제나 승인 필요한 작업은 임의로 확장하지 않음

### Reviewer

Reviewer는 코드 검토와 최종 검증을 함께 담당한다.

- 명세 누락, 정확성, 회귀, 오류 처리, 보안, 유지보수성 검토
- 일반 품질 검토 후 과설계와 불필요한 복잡성 점검
- 완료 조건을 정상·오류·경계·회귀 테스트 항목으로 변환
- 가장 좁은 관련 테스트부터 실행하고 가능한 전체 회귀 검증 수행
- 실패 시 명령, 입력, 환경, 실제 출력을 포함한 재현 근거 보고
- 실행하지 못한 항목은 통과로 처리하지 않고 `미검증`으로 분류
- 중요 결함이 없으면 억지 지적 없이 검토 범위, 검증 결과, 남은 위험 보고

Reviewer는 검토·테스트 요청만으로 제품 코드를 수정하지 않는다. 수정이 필요하면 PM이 Developer에게 전달할 수 있는 구체적인 반려 조건을 작성한다.

## Workflow

Phase 1에서는 사용자가 역할 간 결과를 직접 전달한다.

```text
1. 사용자가 PM에게 요구사항 전달
2. PM이 명세와 Developer Brief 작성
3. 사용자가 Brief를 Developer에게 전달
4. Developer가 구현과 자체 검증 결과 작성
5. 사용자가 결과를 Reviewer에게 전달
6. Reviewer가 코드 검토와 테스트 실행
7-a. 승인: 사용자가 PM에게 결과 전달, PM이 최종 정리
7-b. 반려: 사용자가 PM에게 결과 전달, PM이 Developer 재작업 지시 작성
```

Phase 2에서는 동일한 상태 전이를 유지하면서 `/next`로 다음 역할에 전달한다. `/next`의 메시지 형식, 대상 결정, 실패 복구는 별도 Phase 2 설계에서 정한다.

## Runtime 구조 변경

```text
Role
  ├─ pm
  ├─ developer
  └─ reviewer

tmux session
  ├─ window: pm
  ├─ window: developer
  └─ window: reviewer

prompts
  ├─ pm.md
  ├─ developer.md
  └─ reviewer.md
```

- `Role.TESTER`, `Role.DOCS`를 Domain Enum에서 제거한다.
- 기본 설정과 `config show`에는 세 역할만 나타난다.
- `roles.tester.adapter`, `roles.docs.adapter`는 새 설정 명령에서 지원하지 않는다.
- `prompts/tester.md`, `prompts/docs.md`는 책임 병합 후 제거한다.
- Session의 정상 상태는 정확히 세 개의 역할 Window가 존재하는 경우다.

## 기존 데이터 자동 전환

Runtime 데이터는 대상 프로젝트가 아니라 `ATCODE_HOME`에만 있으므로 그 안에서 호환 처리한다.

### 설정

기존 schema version 1 설정에 `tester`와 `docs`가 있을 수 있다.

- schema version 1을 유지한다.
- 설정을 읽을 때 `tester`와 `docs`만 알려진 legacy key로 인정하고 유효성 검사 전에 제거한 사본을 사용한다.
- 다른 알 수 없는 역할 이름은 기존처럼 오류로 처리한다.
- `atcode doctor`, `config show`처럼 읽기 전용인 명령은 원본 파일을 수정하지 않는다.
- 이후 `config set` 또는 `config unset`으로 같은 설정 파일을 저장하면 legacy key가 빠진 정규화된 값을 기록한다.
- `config show`는 항상 세 역할만 출력한다.

### 상태

- schema version 1 상태의 역할 목록에서 `tester`와 `docs` 항목은 읽을 때 제외한다.
- 다른 알 수 없는 역할은 손상된 상태로 처리한다.
- 다음 `status`, `stop`, `start`가 상태를 기록할 때 세 역할만 저장한다.
- 읽기만 하는 과정에서는 상태 파일을 수정하지 않는다.

### 실행 중인 기존 tmux 세션

- 5역할 Window가 남은 세션은 새 세 역할 구조와 정확히 일치하지 않으므로 `degraded`로 판단한다.
- `atcode start`는 해당 세션을 임의로 부분 수정하지 않고 기존 안내대로 `atcode stop`, `atcode start`를 요구한다.
- `stop`은 전체 기존 세션을 종료하고, 다음 `start`는 세 Window만 새로 만든다.
- 자동 `send-keys`, Window 내용 캡처, 기존 대화 이전은 수행하지 않는다.

## Commands

사용자 명령은 변경하지 않는다.

```bash
atcode init
atcode doctor
atcode start
atcode attach
atcode status
atcode stop
atcode config show
```

기존 5역할 세션의 전환 절차:

```bash
atcode status
atcode stop
atcode start
atcode attach
```

제거된 역할 키는 `ERROR CONFIG_KEY_INVALID`를 반환한다.

개발 검증 명령:

```bash
python3 -m pytest -q
python3 -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

## Project Structure

```text
src/atcode/domain/models.py
  세 역할 Domain Enum과 직렬화 순서
src/atcode/application/configuration.py
  세 역할 기본값, 설정 검증, legacy 설정 정규화
src/atcode/infrastructure/storage/state.py
  legacy 역할을 제외한 상태 읽기
src/atcode/application/sessions.py
  정확한 세 Window 정상 상태 판정
prompts/pm.md
  기존 Docs의 사실 대조·최종 정리·한국어 윤문 책임 병합
prompts/reviewer.md
  기존 Tester의 테스트 설계·실행·증거 보고 책임 병합
prompts/tester.md, prompts/docs.md
  책임 병합 후 제거
tests/unit, tests/integration
  세 역할 계약과 legacy 데이터 전환 검증
README.md
  세 역할 Workflow와 기존 세션 전환 안내
```

## Code Style

legacy 데이터는 입력 객체를 직접 바꾸지 않고 정규화된 사본으로 처리한다.

```python
LEGACY_ROLES = frozenset({"tester", "docs"})


def normalize_roles(value: dict[str, object]) -> dict[str, object]:
    normalized = deepcopy(value)
    roles = normalized.get("roles")
    if isinstance(roles, dict):
        for role in LEGACY_ROLES:
            roles.pop(role, None)
    return normalized
```

실제 구현에서는 설정 전체와 상태 항목의 타입 검증 순서를 보존한다. legacy 이름이라는 이유만으로 잘못된 최상위 구조나 schema version을 허용하지 않는다.

## Testing Strategy

필수 테스트:

1. `tuple(Role)`이 `pm`, `developer`, `reviewer`만 포함한다.
2. 기본 설정과 `config show`가 세 역할 모두 Codex로 출력된다.
3. 새 SessionSpec이 세 역할 Window만 생성한다.
4. PM Prompt에 최종 문서 정리와 사실 대조 책임이 포함된다.
5. Reviewer Prompt에 정상·오류·경계·회귀 테스트와 미검증 보고 책임이 포함된다.
6. 제거된 역할의 Prompt를 Runtime이 찾거나 렌더링하지 않는다.
7. legacy 설정의 Tester·Docs 항목은 읽을 수 있고 유효 설정에는 나타나지 않는다.
8. legacy 설정의 다른 알 수 없는 역할은 계속 실패한다.
9. legacy 상태의 Tester·Docs 항목은 읽을 수 있고 다음 저장 결과에는 나타나지 않는다.
10. 5-window 세션은 `degraded`, 정확한 3-window 세션은 `running`이다.
11. 5-window 세션을 `stop` 후 `start`하면 3-window 세션이 생성된다.
12. 대상 프로젝트 파일 목록은 역할 전환 전후로 변하지 않는다.

## Boundaries

### Always

- 역할 책임을 PM, Developer, Reviewer Prompt에 명시한다.
- legacy 데이터는 `tester`, `docs`만 제한적으로 허용한다.
- 기존 세션의 대화 내용을 보존할 수 없다는 점을 전환 전에 안내한다.
- 설정과 상태는 `ATCODE_HOME`에서만 읽고 쓴다.
- 전체 테스트를 통과한 뒤 역할 전환 완료를 보고한다.

### Ask first

- 기존 Prompt 파일 `prompts/tester.md`, `prompts/docs.md` 삭제
- schema version 변경
- 사용자 정의 역할이나 역할 활성화 설정 추가
- Phase 2 메시지 전달 기능 구현

### Never

- 대상 프로젝트에 migration 파일, 설정, 로그, Workspace를 만들지 않는다.
- 기존 tmux pane 내용을 캡처하거나 새 역할로 자동 전송하지 않는다.
- `tester`, `docs` 외의 알 수 없는 역할을 조용히 무시하지 않는다.
- Phase 1에 `/next`, `send-keys`, `capture-pane`, Task Queue를 추가하지 않는다.
- Reviewer가 테스트를 실행했다는 근거 없이 검증 완료로 처리하지 않는다.

## Success Criteria

1. 새 프로젝트의 `atcode start`가 세 개의 Codex Window만 생성한다.
2. 세 역할만으로 명세, 구현, 검토, 테스트, 최종 정리 흐름이 완결된다.
3. 기존 설정과 상태의 Tester·Docs 항목 때문에 `doctor`, `config show`, `status`, `stop`이 실패하지 않는다.
4. 기존 5-window 세션은 사용자에게 `stop`·`start` 전환 절차를 요구한다.
5. 전환 후 설정 출력, 상태, Prompt, tmux Window에 Tester와 Docs가 나타나지 않는다.
6. 작업 대상 프로젝트에는 AtCode 관리 흔적이 생기지 않는다.
7. 전체 자동 테스트와 Bash/Python 정적 검증이 통과한다.

## Phase 2 연결점

Phase 2 Workflow의 기본 진행 명령은 `/next`로 설계한다.

```text
PM /next → Developer
Developer /next → Reviewer
Reviewer 승인 /next → PM
```

Reviewer 반려 흐름, 메시지 저장 형식, 전송 실패 복구, pane 동시 보기, 역할 추가·수정·삭제는 Phase 2 설계에서 확정한다.

## Open Questions

없음. 역할 수, 책임 병합, legacy 처리, Phase 1과 Phase 2의 경계는 승인된 상태다.
