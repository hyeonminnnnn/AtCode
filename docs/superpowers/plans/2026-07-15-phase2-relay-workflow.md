# Phase 2 Relay Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PM, Developer, Reviewer를 기본 3-Pane으로 실행하고 구조화된 최신 인계를 `Ctrl+b Enter` 또는 `atcode next`로 다음 역할에 안전하게 전달하며 재부팅 후 현재 Workflow를 복구한다.

**Architecture:** 고정 상태 전이와 Handoff 검증은 Application Service에 두고, tmux Capture·Buffer Paste·Focus·Key Binding은 확장된 Terminal Backend Port 뒤에 둔다. 역할 Prompt, Workflow 상태, 최신 Handoff는 `ATCODE_HOME/projects/<project-id>/workspace/`에 분리 저장하고 대상 프로젝트에는 Runtime 관리 파일을 만들지 않는다.

**Tech Stack:** Python 3.11+, 표준 라이브러리, `argparse`, JSON Atomic Replace, tmux 3.x, pytest

## Global Constraints

- 기본 Platform은 WSL2/Linux이며 Terminal Backend는 tmux다.
- 새 외부 Python Dependency를 추가하지 않는다.
- 활성 역할은 `pm`, `developer`, `reviewer` 세 개로 고정한다.
- 프로젝트당 활성 Workflow는 하나만 허용한다.
- 기본 Layout은 `panes`, 선택 Layout은 `windows`다.
- Runtime 데이터는 `ATCODE_HOME`에만 기록하고 대상 프로젝트에는 AtCode 관리 파일을 만들지 않는다.
- 역할 Prompt에 Handoff를 누적하지 않고 `handoff.json`에는 최신 인계 하나만 저장한다.
- Handoff 본문은 UTF-8 32 KiB 이하로 제한한다.
- Relay의 보장 수준은 At Least Once이며 Pending 재시도는 같은 Transfer ID를 재사용한다.
- Configuration schema는 version 1을 유지하고 Runtime State는 version 2로 기록한다.
- Phase 1 Runtime State version 1은 읽을 수 있어야 한다.
- 전체 대화, Handoff 이력, Task Queue, Database, Web UI, 자유 역할 편집, 실시간 Layout 변환, 병렬 Team은 구현하지 않는다.
- 모든 변경은 실패 테스트부터 작성하고 관련 테스트 통과 후 작은 Commit으로 기록한다.

---

## File Structure

```text
src/atcode/domain/models.py
  Layout, Role Endpoint, Runtime State v2, Workflow, Handoff 값 객체
src/atcode/ports/backend.py
  Session과 Role 단위 Terminal 기능 계약
src/atcode/ports/storage.py
  Project Lock, Workflow Store 계약
src/atcode/application/configuration.py
  layout 설정의 기본값, 병합, 검증
src/atcode/application/handoffs.py
  최신 Handoff Marker Parsing과 검증
src/atcode/application/workflow.py
  고정 상태 전이, Pending 재시도, 상태 복구
src/atcode/application/prompts.py
  역할 Prompt Render와 Active/Waiting 시작 Prompt 조합
src/atcode/application/sessions.py
  Layout 기반 Session 시작과 재부팅 재개
src/atcode/application/diagnostics.py
  Workflow JSON, Role Endpoint, Key Binding 진단
src/atcode/infrastructure/process.py
  Shell 없이 stdin Text를 전달하는 Subprocess 경계
src/atcode/infrastructure/tmux_backend.py
  3-Pane/3-Window, Capture, Buffer Paste, Focus, Binding
src/atcode/infrastructure/storage/lock.py
  프로젝트별 Runtime File Lock
src/atcode/infrastructure/storage/workflow.py
  workflow.json, handoff.json Atomic Store
src/atcode/infrastructure/storage/state.py
  Runtime State v1 읽기와 v2 쓰기
src/atcode/cli.py
  next, start --fresh, Workflow 상태 출력
src/atcode/bootstrap.py
  새 Store와 Service 조립
prompts/pm.md
prompts/developer.md
prompts/reviewer.md
  역할별 Handoff 출력과 Transfer 중복 처리 계약
tests/unit/
  Domain, Parser, Store, Workflow, Session, Backend 단위 검증
tests/integration/
  CLI Relay, 복구, 호환, 대상 프로젝트 무흔적 검증
README.md
  Phase 2 사용자 명령과 단축키
```

### Task 1: Layout 설정과 Runtime State v2 기반

**Files:**
- Modify: `src/atcode/domain/models.py`
- Modify: `src/atcode/application/configuration.py`
- Modify: `src/atcode/infrastructure/storage/state.py`
- Modify: `tests/unit/test_configuration.py`
- Modify: `tests/unit/test_state_store.py`

**Interfaces:**
- Produces: `Layout`, `RuntimeConfig.layout`, `RuntimeState.layout`, Window 이름을 제거한 `RoleRuntime`
- Produces: Configuration key `layout` with values `panes | windows`
- Produces: Runtime State schema version 2 writer and schema version 1 reader

- [ ] **Step 1: Layout 기본값과 설정 변경 실패 테스트 작성**

`tests/unit/test_configuration.py`에 다음 테스트를 추가하고 기존 `RuntimeConfig` 생성 Assertion은 `layout`을 포함하도록 바꾼다.

```python
from atcode.domain.models import Layout


def test_default_layout_is_panes(tmp_path: Path) -> None:
    service, _store = make_service(tmp_path)

    config = service.effective(None)

    assert config.layout is Layout.PANES


def test_project_layout_override_round_trips(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)

    service.set(project, "layout", "windows", global_scope=False)

    assert service.get(project, "layout") == "windows"
    assert service.effective(project).layout is Layout.WINDOWS


def test_unknown_layout_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)

    with pytest.raises(AtCodeError, match="CONFIG_VALUE_INVALID"):
        service.set(project, "layout", "grid", global_scope=False)
```

- [ ] **Step 2: Runtime State v1 호환과 v2 쓰기 실패 테스트 작성**

`tests/unit/test_state_store.py`의 `make_state()`를 새 Model에 맞추고 다음 테스트를 추가한다.

```python
from atcode.domain.models import Layout


def test_state_writer_uses_schema_two_and_logical_roles(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonStateStore(runtime_home)

    store.write(project, make_state(project))

    value = json.loads(
        (runtime_home / "projects" / project.project_id / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert value["schemaVersion"] == 2
    assert value["layout"] == "panes"
    assert value["roles"] == [
        {"role": role.value, "adapter": "codex", "endpoint": role.value}
        for role in Role
    ]


def test_schema_one_state_reads_as_windows_layout(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    path = runtime_home / "projects" / project.project_id / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "projectId": project.project_id,
                "backend": "tmux",
                "backendSession": f"atcode-{project.project_id}",
                "status": "running",
                "startedAt": None,
                "stoppedAt": None,
                "roles": [
                    {"role": role.value, "adapter": "codex", "window": role.value}
                    for role in Role
                ],
                "lastError": None,
            }
        ),
        encoding="utf-8",
    )

    state = JsonStateStore(runtime_home).read(project)

    assert state is not None
    assert state.layout is Layout.WINDOWS
    assert state.roles == tuple(
        RoleRuntime(role, "codex", role.value) for role in Role
    )
```

- [ ] **Step 3: 두 테스트 파일을 실행해 실패 확인**

Run: `python -m pytest -q tests/unit/test_configuration.py tests/unit/test_state_store.py`

Expected: `Layout` Import 또는 `RuntimeConfig.layout` 부재로 FAIL.

- [ ] **Step 4: Domain과 Configuration 최소 구현**

`src/atcode/domain/models.py`에 다음 Enum과 변경된 값 객체를 반영한다.

```python
class Layout(str, Enum):
    PANES = "panes"
    WINDOWS = "windows"


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str
    roles: Mapping[Role, RoleAssignment]
    layout: Layout = Layout.PANES

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "backend": self.backend,
            "layout": self.layout.value,
            "roles": {
                role.value: {"adapter": self.roles[role].adapter} for role in Role
            },
        }


@dataclass(frozen=True)
class RoleRuntime:
    role: Role
    adapter: str
    endpoint: str


@dataclass(frozen=True)
class RuntimeState:
    project_id: str
    backend: str
    session_name: str
    status: Lifecycle
    started_at: str | None
    stopped_at: str | None
    roles: tuple[RoleRuntime, ...]
    last_error: str | None = None
    layout: Layout = Layout.PANES
```

`src/atcode/application/configuration.py`에서 `_DEFAULT`에 `"layout": "panes"`를 추가하고 `effective()`, `get()`, `set()`, `unset()`, `_validate_key()`, `_validate_value()`, `_validate_layer()`가 `layout`을 처리하게 한다. `effective()`의 반환은 다음 형태를 사용한다.

```python
return RuntimeConfig(
    backend=merged["backend"],
    roles={
        role: RoleAssignment(merged["roles"][role.value]["adapter"])
        for role in Role
    },
    layout=Layout(merged["layout"]),
)
```

Configuration object의 허용 Top-Level Key는 정확히 `schemaVersion`, `backend`, `layout`, `roles`다. `layout` 값 검증은 `value in {layout.value for layout in Layout}`를 사용한다.

- [ ] **Step 5: Runtime State v1/v2 Reader와 v2 Writer 구현**

`src/atcode/infrastructure/storage/state.py`에서 schema 1과 2만 읽는다. schema 1은 `window`를 논리 `endpoint`로 변환하고 `Layout.WINDOWS`를 사용한다. schema 2는 `layout`을 읽고 Role item의 허용 Key를 `role`, `adapter`, `endpoint`로 제한한다. Endpoint는 Role별 안정적인 논리 이름이며 tmux Pane ID를 저장하지 않는다. Writer는 다음 Shape을 사용한다.

```python
{
    "schemaVersion": 2,
    "projectId": state.project_id,
    "backend": state.backend,
    "backendSession": state.session_name,
    "layout": state.layout.value,
    "status": state.status.value,
    "startedAt": state.started_at,
    "stoppedAt": state.stopped_at,
    "roles": [
        {
            "role": item.role.value,
            "adapter": item.adapter,
            "endpoint": item.endpoint,
        }
        for item in state.roles
    ],
    "lastError": state.last_error,
}
```

- [ ] **Step 6: 관련 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_configuration.py tests/unit/test_state_store.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/domain/models.py src/atcode/application/configuration.py src/atcode/infrastructure/storage/state.py tests/unit/test_configuration.py tests/unit/test_state_store.py
git commit -m "feat: add phase two layout and state schema"
```

### Task 2: 구조화된 Handoff Parser와 Domain 값 객체

**Files:**
- Modify: `src/atcode/domain/models.py`
- Create: `src/atcode/application/handoffs.py`
- Create: `tests/unit/test_handoffs.py`

**Interfaces:**
- Produces: `HandoffDecision`, `DeliveryState`, `ParsedHandoff`, `Handoff`
- Produces: `HandoffParser.parse(output: str, role: Role) -> ParsedHandoff`
- Produces: `MAX_HANDOFF_BYTES = 32 * 1024`

- [ ] **Step 1: Parser 실패 테스트 작성**

`tests/unit/test_handoffs.py`를 다음 핵심 사례로 생성한다.

```python
from __future__ import annotations

import pytest

from atcode.application.handoffs import HandoffParser, MAX_HANDOFF_BYTES
from atcode.domain.errors import AtCodeError
from atcode.domain.models import HandoffDecision, Role


def test_parser_returns_latest_complete_handoff() -> None:
    output = """
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
old
</ATCODE_HANDOFF>
progress
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
new
</ATCODE_HANDOFF>
"""

    parsed = HandoffParser().parse(output, Role.PM)

    assert parsed.decision is HandoffDecision.READY
    assert parsed.body == "SUMMARY:\nnew"
    assert parsed.digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("role", "status"),
    [
        (Role.PM, "approved"),
        (Role.DEVELOPER, "rejected"),
        (Role.REVIEWER, "ready"),
    ],
)
def test_parser_rejects_status_not_allowed_for_role(role: Role, status: str) -> None:
    output = (
        "<ATCODE_HANDOFF>\n"
        f"STATUS: {status}\n"
        "SUMMARY:\nbody\n"
        "</ATCODE_HANDOFF>"
    )

    with pytest.raises(AtCodeError, match="HANDOFF_STATUS_INVALID"):
        HandoffParser().parse(output, role)


def test_parser_rejects_missing_complete_block() -> None:
    with pytest.raises(AtCodeError, match="HANDOFF_MISSING"):
        HandoffParser().parse("<ATCODE_HANDOFF>\nSTATUS: ready", Role.PM)


def test_parser_rejects_empty_body() -> None:
    output = "<ATCODE_HANDOFF>\nSTATUS: ready\n</ATCODE_HANDOFF>"

    with pytest.raises(AtCodeError, match="HANDOFF_BODY_INVALID"):
        HandoffParser().parse(output, Role.PM)


def test_parser_rejects_body_over_limit() -> None:
    output = (
        "<ATCODE_HANDOFF>\nSTATUS: ready\n"
        + ("가" * (MAX_HANDOFF_BYTES + 1))
        + "\n</ATCODE_HANDOFF>"
    )

    with pytest.raises(AtCodeError, match="HANDOFF_TOO_LARGE"):
        HandoffParser().parse(output, Role.PM)
```

- [ ] **Step 2: Parser 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_handoffs.py`

Expected: `atcode.application.handoffs`가 없어 FAIL.

- [ ] **Step 3: Handoff Domain 값 객체 추가**

`src/atcode/domain/models.py`에 다음 타입을 추가한다.

```python
class HandoffDecision(str, Enum):
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeliveryState(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"


@dataclass(frozen=True)
class ParsedHandoff:
    decision: HandoffDecision
    body: str
    digest: str


@dataclass(frozen=True)
class Handoff:
    transfer_id: int
    from_role: Role
    to_role: Role
    decision: HandoffDecision
    delivery: DeliveryState
    digest: str
    body: str
    created_at: str
    delivered_at: str | None = None
```

- [ ] **Step 4: Parser 최소 구현**

`src/atcode/application/handoffs.py`에 Marker 추출과 검증을 구현한다.

```python
from __future__ import annotations

import hashlib
import re

from atcode.domain.errors import AtCodeError
from atcode.domain.models import HandoffDecision, ParsedHandoff, Role

MAX_HANDOFF_BYTES = 32 * 1024
_BLOCK = re.compile(r"<ATCODE_HANDOFF>\s*(.*?)\s*</ATCODE_HANDOFF>", re.DOTALL)
_ALLOWED = {
    Role.PM: frozenset({HandoffDecision.READY}),
    Role.DEVELOPER: frozenset({HandoffDecision.READY}),
    Role.REVIEWER: frozenset(
        {HandoffDecision.APPROVED, HandoffDecision.REJECTED}
    ),
}


class HandoffParser:
    def parse(self, output: str, role: Role) -> ParsedHandoff:
        blocks = _BLOCK.findall(output)
        if not blocks:
            raise AtCodeError(
                "HANDOFF_MISSING",
                "A complete ATCODE_HANDOFF block was not found.",
            )
        lines = blocks[-1].strip().splitlines()
        if not lines or not lines[0].startswith("STATUS: "):
            raise AtCodeError("HANDOFF_STATUS_INVALID", "Handoff STATUS is missing.")
        try:
            decision = HandoffDecision(lines[0].removeprefix("STATUS: ").strip())
        except ValueError as error:
            raise AtCodeError(
                "HANDOFF_STATUS_INVALID", "Handoff STATUS is unsupported."
            ) from error
        if decision not in _ALLOWED[role]:
            raise AtCodeError(
                "HANDOFF_STATUS_INVALID",
                f"{role.value} cannot send STATUS {decision.value}.",
            )
        body = "\n".join(lines[1:]).strip()
        if not body:
            raise AtCodeError("HANDOFF_BODY_INVALID", "Handoff body is empty.")
        if len(body.encode("utf-8")) > MAX_HANDOFF_BYTES:
            raise AtCodeError("HANDOFF_TOO_LARGE", "Handoff exceeds 32 KiB.")
        digest_input = f"{role.value}\0{decision.value}\0{body}".encode("utf-8")
        digest = f"sha256:{hashlib.sha256(digest_input).hexdigest()}"
        return ParsedHandoff(decision, body, digest)
```

- [ ] **Step 5: Parser 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_handoffs.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atcode/domain/models.py src/atcode/application/handoffs.py tests/unit/test_handoffs.py
git commit -m "feat: parse structured role handoffs"
```

### Task 3: Project Lock과 Workflow/Handoff Atomic Store

**Files:**
- Modify: `src/atcode/domain/models.py`
- Modify: `src/atcode/ports/storage.py`
- Create: `src/atcode/infrastructure/storage/lock.py`
- Create: `src/atcode/infrastructure/storage/workflow.py`
- Create: `tests/unit/test_workflow_store.py`
- Modify: `tests/unit/test_state_store.py`

**Interfaces:**
- Produces: `WorkflowStatus`, `WorkflowState.initial()`
- Produces: `ProjectLock.locked(project)`
- Produces: `WorkflowStore.read_workflow`, `write_workflow`, `read_handoff`, `write_handoff`, `delete_handoff`
- Produces: `JsonProjectLock`, `JsonWorkflowStore`

- [ ] **Step 1: Workflow Store 실패 테스트 작성**

`tests/unit/test_workflow_store.py`에 다음 테스트를 작성한다.

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    Project,
    Role,
    WorkflowState,
    WorkflowStatus,
)
from atcode.infrastructure.storage.workflow import JsonWorkflowStore


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    return Project("target-1234567890", "target", root, "created")


def make_handoff(body: str = "SUMMARY:\nwork") -> Handoff:
    return Handoff(
        transfer_id=1,
        from_role=Role.PM,
        to_role=Role.DEVELOPER,
        decision=HandoffDecision.READY,
        delivery=DeliveryState.DELIVERED,
        digest="sha256:abc",
        body=body,
        created_at="2026-07-15T00:00:00+00:00",
        delivered_at="2026-07-15T00:00:01+00:00",
    )


def test_missing_workflow_reads_as_idle_pm(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    store = JsonWorkflowStore(tmp_path / "runtime")

    assert store.read_workflow(project) == WorkflowState.initial()


def test_workflow_and_handoff_round_trip_under_runtime_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonWorkflowStore(runtime_home)
    workflow = WorkflowState(
        WorkflowStatus.ACTIVE,
        Role.DEVELOPER,
        1,
        1,
        {Role.PM: "sha256:abc"},
        "2026-07-15T00:00:01+00:00",
    )

    store.write_workflow(project, workflow)
    store.write_handoff(project, make_handoff())

    assert store.read_workflow(project) == workflow
    assert store.read_handoff(project) == make_handoff()
    assert not (project.root / "workflow.json").exists()
    assert not (project.root / "handoff.json").exists()


def test_next_handoff_replaces_previous_file(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonWorkflowStore(runtime_home)

    store.write_handoff(project, make_handoff("SUMMARY:\nfirst"))
    store.write_handoff(project, make_handoff("SUMMARY:\nsecond"))

    assert store.read_handoff(project).body == "SUMMARY:\nsecond"
    workspace = runtime_home / "projects" / project.project_id / "workspace"
    assert {path.name for path in workspace.iterdir()} == {"handoff.json"}


def test_invalid_workflow_json_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    path = (
        tmp_path
        / "runtime"
        / "projects"
        / project.project_id
        / "workspace"
        / "workflow.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")

    with pytest.raises(AtCodeError, match="WORKFLOW_INVALID"):
        JsonWorkflowStore(tmp_path / "runtime").read_workflow(project)
```

- [ ] **Step 2: Store 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_workflow_store.py`

Expected: Workflow Domain과 Store가 없어 FAIL.

- [ ] **Step 3: Workflow Domain과 Storage Port 구현**

`src/atcode/domain/models.py`에 다음 타입을 추가한다.

```python
class WorkflowStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    REWORK = "rework"
    COMPLETE = "complete"


@dataclass(frozen=True)
class WorkflowState:
    status: WorkflowStatus
    current_role: Role
    round: int
    last_transfer_id: int
    last_digests: Mapping[Role, str]
    updated_at: str | None

    @classmethod
    def initial(cls) -> "WorkflowState":
        return cls(WorkflowStatus.IDLE, Role.PM, 0, 0, {}, None)
```

`src/atcode/ports/storage.py`에 다음 Protocol을 추가한다. 이 Task의 Commit에서 기존 SessionService가 계속 동작하도록 `StateStore.locked()`는 아직 유지한다.

```python
class ProjectLock(Protocol):
    def locked(self, project: Project) -> AbstractContextManager[None]: ...


class WorkflowStore(Protocol):
    def read_workflow(self, project: Project) -> WorkflowState: ...

    def write_workflow(self, project: Project, state: WorkflowState) -> None: ...

    def read_handoff(self, project: Project) -> Handoff | None: ...

    def write_handoff(self, project: Project, handoff: Handoff) -> None: ...

    def delete_handoff(self, project: Project) -> None: ...
```

- [ ] **Step 4: Lock 책임을 별도 구현으로 이동**

`src/atcode/infrastructure/storage/lock.py`에 `JsonStateStore.locked()`와 같은 OS별 Lock 동작을 `JsonProjectLock`으로 구현한다. Lock 경로는 계속 `ATCODE_HOME/projects/<project-id>/state.lock`을 사용한다. 기존 `JsonStateStore.locked()`는 Task 8에서 SessionService 의존성을 전환할 때 제거하므로 이 Commit의 전체 회귀가 깨지지 않는다.

```python
class JsonProjectLock:
    def __init__(self, runtime_home: Path) -> None:
        self._home = runtime_home

    @contextmanager
    def locked(self, project: Project) -> Iterator[None]:
        path = self._home / "projects" / project.project_id / "state.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            _acquire(stream)
            try:
                yield
            finally:
                _release(stream)
```

`tests/unit/test_state_store.py`의 Lock 테스트는 `JsonProjectLock`을 직접 검증하도록 Import와 생성 대상을 변경한다.

- [ ] **Step 5: JsonWorkflowStore 구현**

`src/atcode/infrastructure/storage/workflow.py`에서 경로를 다음처럼 고정한다.

```python
def _workspace(self, project: Project) -> Path:
    return self._home / "projects" / project.project_id / "workspace"


def _workflow_path(self, project: Project) -> Path:
    return self._workspace(project) / "workflow.json"


def _handoff_path(self, project: Project) -> Path:
    return self._workspace(project) / "handoff.json"
```

Workflow JSON은 `schemaVersion`, `status`, `currentRole`, `round`, `lastTransferId`, `lastDigests`, `updatedAt`만 허용한다. Handoff JSON은 설계 문서의 Key만 허용한다. Role Key가 있는 `lastDigests`는 `Role`로 변환하고 알 수 없는 Role, 음수 ID/Round, 불일치 Timestamp를 `WORKFLOW_INVALID` 또는 `HANDOFF_INVALID`로 감싼다. 쓰기는 `write_json_atomic()`을 사용하고 삭제는 `Path.unlink(missing_ok=True)`를 사용한다.

- [ ] **Step 6: Store와 Lock 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_workflow_store.py tests/unit/test_state_store.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/domain/models.py src/atcode/ports/storage.py src/atcode/infrastructure/storage/lock.py src/atcode/infrastructure/storage/workflow.py tests/unit/test_workflow_store.py tests/unit/test_state_store.py
git commit -m "feat: persist current relay workflow"
```

### Task 4: Role Endpoint 중심 tmux Layout

**Files:**
- Modify: `src/atcode/domain/models.py`
- Modify: `src/atcode/ports/backend.py`
- Modify: `src/atcode/application/sessions.py`
- Modify: `src/atcode/application/diagnostics.py`
- Modify: `src/atcode/infrastructure/tmux_backend.py`
- Modify: `tests/unit/test_tmux_backend.py`
- Modify: `tests/unit/test_sessions.py`
- Modify: `tests/unit/test_diagnostics.py`
- Modify: `tests/integration/test_cli.py`

**Interfaces:**
- Produces: `RoleSpec`, `RoleEndpoint`, Layout을 가진 `SessionSpec`과 `SessionSnapshot`
- Produces: `TmuxBackend.create_session()`의 panes/windows 구현
- Consumes: Task 1의 `Layout`

- [ ] **Step 1: 새 Session Model을 사용하는 Backend 실패 테스트 작성**

`tests/unit/test_tmux_backend.py`의 `session_spec()`을 다음 Shape으로 바꾼다.

```python
from dataclasses import dataclass

from atcode.domain.models import Layout, Role, RoleSpec


def session_spec(tmp_path: Path, layout: Layout = Layout.PANES) -> SessionSpec:
    roles = tuple(
        RoleSpec(
            role=role,
            cwd=tmp_path,
            launch=LaunchSpec(
                executable="agent-cli",
                arguments=(f"{role.value} prompt",),
                environment={"ATCODE_ROLE": role.value},
            ),
        )
        for role in Role
    )
    return SessionSpec("atcode-target-1234567890", tmp_path, layout, roles)
```

같은 파일의 Runner 기록 형식을 stdin까지 보존하도록 다음처럼 바꾸고 기존 Assertion은 `call.argv`를 사용한다.

```python
@dataclass(frozen=True)
class RecordedCall:
    argv: tuple[str, ...]
    input_text: str | None


class FakeRunner:
    def __init__(self, results: Sequence[tuple[int, str, str]]) -> None:
        self._results = list(results)
        self.calls: list[RecordedCall] = []
        self.interactive_calls: list[tuple[str, ...]] = []

    def run(self, argv, *, input_text=None, **_kwargs) -> CommandResult:
        command = tuple(argv)
        self.calls.append(RecordedCall(command, input_text))
        returncode, stdout, stderr = self._results.pop(0)
        return CommandResult(command, returncode, stdout, stderr)

    def run_interactive(self, argv, **_kwargs) -> int:
        self.interactive_calls.append(tuple(argv))
        return 0
```

새 Layout Test는 다음 결정적 Runner를 사용한다.

```python
class LayoutRunner(FakeRunner):
    def __init__(
        self,
        layout: Layout,
        *,
        initial_exists: bool = False,
        fail_operation: str | None = None,
        missing_role: Role | None = None,
    ) -> None:
        super().__init__([])
        self.layout = layout
        self._split_ids = iter(("%2", "%3"))
        self._exists = initial_exists
        self._fail_operation = fail_operation
        self._missing_role = missing_role

    def run(self, argv, *, input_text=None, **_kwargs) -> CommandResult:
        command = tuple(argv)
        self.calls.append(RecordedCall(command, input_text))
        if "has-session" in command:
            return CommandResult(command, 0 if self._exists else 1, "", "")
        if self._fail_operation is not None and self._fail_operation in command:
            return CommandResult(command, 1, "", "forced failure")
        if "new-session" in command:
            self._exists = True
            return CommandResult(command, 0, "", "")
        if "kill-session" in command:
            self._exists = False
            return CommandResult(command, 0, "", "")
        if "split-window" in command:
            return CommandResult(command, 0, next(self._split_ids) + "\n", "")
        if "list-panes" in command:
            if self.layout is Layout.PANES:
                rows = (
                    "pm\tteam\t%1\t1\n"
                    "developer\tteam\t%2\t0\n"
                    "reviewer\tteam\t%3\t0\n"
                )
            else:
                rows = (
                    "pm\tpm\t%1\t1\n"
                    "developer\tdeveloper\t%2\t0\n"
                    "reviewer\treviewer\t%3\t0\n"
                )
            if self._missing_role is not None:
                rows = "\n".join(
                    line
                    for line in rows.splitlines()
                    if not line.startswith(self._missing_role.value + "\t")
                ) + "\n"
            return CommandResult(command, 0, rows, "")
        return CommandResult(command, 0, "", "")
```

기존 Rollback Test는 `LayoutRunner(Layout.PANES, missing_role=Role.REVIEWER)`, `LayoutRunner(Layout.PANES, fail_operation="split-window")`, `LayoutRunner(Layout.PANES, initial_exists=True)`를 각각 사용해 Window Verification 실패, 부분 생성 실패, 기존 Session 보존을 검증한다. Kill Assertion은 `runner.calls[-1].argv`를 사용한다.

다음 Assertion을 별도 테스트로 추가한다.

```python
def test_create_panes_session_uses_one_window_and_three_role_panes(
    tmp_path: Path,
) -> None:
    runner = LayoutRunner(Layout.PANES)
    backend = TmuxBackend(runner, {})

    backend.create_session(session_spec(tmp_path, Layout.PANES))

    assert sum("new-session" in call.argv for call in runner.calls) == 1
    assert sum("split-window" in call.argv for call in runner.calls) == 2
    assert all("new-window" not in call.argv for call in runner.calls)
    assert any("select-layout" in call.argv for call in runner.calls)
    assert any("pane-border-format" in call.argv for call in runner.calls)


def test_create_windows_session_keeps_three_windows(tmp_path: Path) -> None:
    runner = LayoutRunner(Layout.WINDOWS)
    backend = TmuxBackend(runner, {})

    backend.create_session(session_spec(tmp_path, Layout.WINDOWS))

    assert sum("new-session" in call.argv for call in runner.calls) == 1
    assert sum("new-window" in call.argv for call in runner.calls) == 2
    assert all("split-window" not in call.argv for call in runner.calls)


def test_inspect_session_returns_role_endpoints_from_pane_metadata() -> None:
    runner = FakeRunner(
        [
            (0, "", ""),
            (
                0,
                "pm\tteam\t%1\t1\n"
                "developer\tteam\t%2\t0\n"
                "reviewer\tteam\t%3\t0\n",
                "",
            ),
        ]
    )
    backend = TmuxBackend(runner, {})

    snapshot = backend.inspect_session("atcode-target-1234567890")

    assert snapshot.layout is Layout.PANES
    assert tuple(endpoint.role for endpoint in snapshot.endpoints) == tuple(Role)
    assert snapshot.active_role is Role.PM
```

- [ ] **Step 2: Backend와 Session 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_tmux_backend.py tests/unit/test_sessions.py`

Expected: `RoleSpec`, `RoleEndpoint`, 새 `SessionSpec` Field가 없어 FAIL.

- [ ] **Step 3: Role Endpoint Domain과 Port 구현**

`src/atcode/domain/models.py`에서 `WindowSpec`을 `RoleSpec`으로 교체하고 Session Model을 다음처럼 변경한다.

```python
@dataclass(frozen=True)
class RoleSpec:
    role: Role
    cwd: Path
    launch: LaunchSpec


@dataclass(frozen=True)
class SessionSpec:
    session_name: str
    project_root: Path
    layout: Layout
    roles: tuple[RoleSpec, ...]


@dataclass(frozen=True)
class RoleEndpoint:
    role: Role
    window: str
    pane: str
    active: bool = False


@dataclass(frozen=True)
class SessionSnapshot:
    session_name: str
    exists: bool
    layout: Layout | None = None
    endpoints: tuple[RoleEndpoint, ...] = ()

    @property
    def active_role(self) -> Role | None:
        return next((item.role for item in self.endpoints if item.active), None)

    @classmethod
    def stopped(cls, session_name: str) -> "SessionSnapshot":
        return cls(session_name=session_name, exists=False)
```

`src/atcode/ports/backend.py`의 Lifecycle Method Signature는 새 `SessionSpec`과 `SessionSnapshot`을 그대로 사용한다.

- [ ] **Step 4: TmuxBackend panes/windows 생성과 Inspection 구현**

`panes` Layout은 PM을 `team` Window의 첫 Pane으로 시작하고 Developer와 Reviewer를 `split-window -d -P -F '#{pane_id}'`로 만든다. 각 Pane 생성 직후 다음 형태로 Metadata를 지정한다.

```python
self._run_checked(
    ("tmux", "set-option", "-p", "-t", pane_id, "@atcode_role", role.value),
    "set-role-metadata",
)
```

세 Pane 생성 후 `select-layout tiled`, Window-Local `pane-border-status top`, `pane-border-format ' #{@atcode_role} '`, PM `select-pane`을 실행한다. `windows` Layout은 기존 생성 흐름을 유지하면서 각 단일 Pane에 같은 Metadata를 설정한다.

Inspection은 다음 Format의 `tmux list-panes -s` 한 번으로 Role Endpoint를 만든다.

```text
#{@atcode_role}\t#{window_name}\t#{pane_id}\t#{pane_active}
```

모든 Endpoint Window가 `team` 하나면 `Layout.PANES`, 각 Role마다 고유 Window면 `Layout.WINDOWS`, 그 외는 `layout=None`으로 반환해 Degraded 판정을 가능하게 한다.

- [ ] **Step 5: SessionService의 Spec 생성과 상태 판정 임시 적응**

`tests/unit/test_sessions.py` FakeConfig는 `RuntimeConfig("tmux", roles, Layout.PANES)`를 반환한다. FakeBackend는 `SessionSpec.roles`로 `RoleEndpoint`를 만들고 SessionService는 `RoleSpec`을 생성한다. 상태 판정은 다음 조건을 모두 만족할 때만 RUNNING이다.

```python
expected_roles = set(Role)
actual_roles = {endpoint.role for endpoint in snapshot.endpoints}
running = snapshot.exists and actual_roles == expected_roles and snapshot.layout is config.layout
```

`src/atcode/application/diagnostics.py`와 `tests/unit/test_diagnostics.py`의 Session 일치 판정도 `snapshot.endpoints`의 Role 집합을 사용하도록 바꾼다. `tests/integration/test_cli.py` FakeBackend는 `spec.roles`와 `spec.layout`로 `RoleEndpoint(role, window, pane, active)`를 생성한다. panes Layout의 Window는 모두 `team`, windows Layout의 Window는 `role.value`, Pane은 순서대로 `%1`, `%2`, `%3`을 사용한다.

- [ ] **Step 6: Backend와 Session 테스트 통과 확인**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/domain/models.py src/atcode/ports/backend.py src/atcode/application/sessions.py src/atcode/application/diagnostics.py src/atcode/infrastructure/tmux_backend.py tests/unit/test_tmux_backend.py tests/unit/test_sessions.py tests/unit/test_diagnostics.py tests/integration/test_cli.py
git commit -m "feat: add role based tmux layouts"
```

### Task 5: tmux Capture, 안전한 전달, Focus, Next Binding

**Files:**
- Modify: `src/atcode/infrastructure/process.py`
- Modify: `src/atcode/ports/backend.py`
- Modify: `src/atcode/infrastructure/tmux_backend.py`
- Create: `tests/unit/test_process.py`
- Modify: `tests/unit/test_tmux_backend.py`

**Interfaces:**
- Produces: `SubprocessRunner.run(..., input_text: str | None = None)`
- Produces: `TerminalBackend.read_role_output`, `deliver_text`, `focus_role`, `install_next_action`, `next_action_probe`, `display_message`
- Consumes: Task 4의 Role Metadata Endpoint

- [ ] **Step 1: stdin Text와 Relay Backend 실패 테스트 작성**

`tests/unit/test_process.py`에 `subprocess.run` Mock을 사용해 Shell 없이 input이 전달되는지 검증한다.

```python
from unittest.mock import patch

from atcode.infrastructure.process import SubprocessRunner


@patch("atcode.infrastructure.process.subprocess.run")
def test_runner_passes_text_to_stdin_without_shell(mock_run) -> None:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = ""

    SubprocessRunner().run(("tmux", "load-buffer", "-"), input_text="$(touch bad)")

    assert mock_run.call_args.kwargs["input"] == "$(touch bad)"
    assert mock_run.call_args.kwargs["shell"] is False
```

`tests/unit/test_tmux_backend.py`에 다음 동작 테스트를 추가한다.

```python
def test_read_role_output_captures_only_resolved_role_pane() -> None:
    rows = (
        "pm\tteam\t%1\t1\n"
        "developer\tteam\t%2\t0\n"
        "reviewer\tteam\t%3\t0\n"
    )
    runner = FakeRunner(
        [(0, "", ""), (0, rows, ""), (0, "developer output", "")]
    )
    backend = TmuxBackend(runner, {})

    output = backend.read_role_output("atcode-target-1234567890", Role.DEVELOPER)

    assert output == "developer output"
    assert runner.calls[-1].argv == (
        "tmux", "capture-pane", "-p", "-S", "-", "-t", "%2"
    )


def test_deliver_text_uses_tmux_buffer_stdin_and_never_shell_content() -> None:
    body = "line 1\n$(touch bad) `echo bad`\nline 3"
    rows = (
        "pm\tteam\t%1\t1\n"
        "developer\tteam\t%2\t0\n"
        "reviewer\tteam\t%3\t0\n"
    )
    runner = FakeRunner(
        [
            (0, "", ""),
            (0, rows, ""),
            (0, "", ""),
            (0, "", ""),
            (0, "", ""),
        ]
    )
    backend = TmuxBackend(runner, {})

    backend.deliver_text("atcode-target-1234567890", Role.DEVELOPER, body)

    load_call = next(call for call in runner.calls if "load-buffer" in call.argv)
    assert load_call.input_text == body
    assert all(body not in item for call in runner.calls for item in call.argv)
    assert any("paste-buffer" in call.argv and "%2" in call.argv for call in runner.calls)
    assert any("send-keys" in call.argv and "Enter" in call.argv for call in runner.calls)


def test_existing_enter_binding_is_not_overwritten() -> None:
    runner = FakeRunner([(0, "bind-key -T prefix Enter display-menu\n", "")])
    backend = TmuxBackend(runner, {})

    result = backend.install_next_action()

    assert result.level is DiagnosticLevel.WARN
    assert all("bind-key" not in call.argv for call in runner.calls)


def test_unbound_enter_key_installs_atcode_next_action() -> None:
    runner = FakeRunner([(1, "", "not bound"), (0, "", "")])
    backend = TmuxBackend(runner, {})

    result = backend.install_next_action()

    assert result.level is DiagnosticLevel.PASS
    binding = runner.calls[-1].argv
    assert "bind-key" in binding
    assert "Enter" in binding
    assert any("atcode next" in item for item in binding)
```

- [ ] **Step 2: Process와 Backend 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_process.py tests/unit/test_tmux_backend.py`

Expected: 새 Runner 인자와 Backend Method가 없어 FAIL.

- [ ] **Step 3: SubprocessRunner stdin 지원 구현**

`SubprocessRunner.run()`에 `input_text: str | None = None`을 추가하고 `subprocess.run()`에 다음 인자를 전달한다.

```python
completed = subprocess.run(
    command,
    cwd=cwd,
    env=process_env,
    input=input_text,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    timeout=timeout,
    check=False,
    shell=False,
)
```

- [ ] **Step 4: Backend Port 확장**

`src/atcode/ports/backend.py`에 다음 Method를 추가한다.

```python
def read_role_output(self, session_name: str, role: Role) -> str: ...

def deliver_text(self, session_name: str, role: Role, text: str) -> None: ...

def focus_role(self, session_name: str, role: Role) -> None: ...

def install_next_action(self) -> DiagnosticResult: ...

def next_action_probe(self) -> DiagnosticResult: ...

def display_message(self, message: str) -> None: ...
```

- [ ] **Step 5: TmuxBackend Relay Method 구현**

Role Endpoint Lookup은 `inspect_session()` 결과에서 정확히 하나를 찾고 없거나 중복이면 `TMUX_ROLE_ENDPOINT_INVALID`를 발생시킨다.

`read_role_output()`은 `capture-pane -p -S - -t <pane>`을 사용한다. `deliver_text()`는 고정 Buffer 이름 `atcode-transfer`에 `load-buffer -`와 `input_text=text`를 사용하고, `paste-buffer -d -b atcode-transfer -t <pane>`, `send-keys -t <pane> Enter` 순서로 실행한다. `focus_role()`은 panes면 `select-pane -t <pane>`, windows면 `select-window -t =<session>:<window>` 후 `select-pane`을 실행한다.

Binding Probe는 `tmux list-keys -T prefix Enter`를 조회한다. 비어 있으면 다음 정적 Action을 등록하고, 기존 AtCode Action이면 PASS, 다른 Action이면 WARN을 반환한다.

```text
atcode next --session "#{session_name}" --pane "#{pane_id}" --notify
```

Binding 문자열에는 사용자 Handoff가 들어가지 않는다. `display_message()`는 `tmux display-message -- <message>`를 argv로 실행한다.

- [ ] **Step 6: Process와 Backend 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_process.py tests/unit/test_tmux_backend.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/infrastructure/process.py src/atcode/ports/backend.py src/atcode/infrastructure/tmux_backend.py tests/unit/test_process.py tests/unit/test_tmux_backend.py
git commit -m "feat: add safe tmux relay primitives"
```

### Task 6: WorkflowService 상태 전이와 Pending 재시도

**Files:**
- Modify: `src/atcode/domain/models.py`
- Create: `src/atcode/application/workflow.py`
- Create: `tests/unit/test_workflow.py`

**Interfaces:**
- Produces: `TransferResult`, `WorkflowService.next`, `current`, `reset`, `reconcile`
- Consumes: `HandoffParser`, `WorkflowStore`, `ProjectLock`, 확장된 `TerminalBackend`

- [ ] **Step 1: 정상 상태 전이 실패 테스트 작성**

`tests/unit/test_workflow.py`에 Memory Store, Fake Lock, Fake Backend를 두고 다음 테스트를 작성한다.

```python
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from atcode.application.handoffs import HandoffParser
from atcode.application.workflow import WorkflowService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    Layout,
    Project,
    Role,
    RoleEndpoint,
    SessionSnapshot,
    WorkflowState,
    WorkflowStatus,
)


class MemoryWorkflowStore:
    def __init__(self, workflow: WorkflowState | None = None) -> None:
        self.workflow = workflow or WorkflowState.initial()
        self.handoff: Handoff | None = None

    def read_workflow(self, _project: Project) -> WorkflowState:
        return self.workflow

    def write_workflow(self, _project: Project, state: WorkflowState) -> None:
        self.workflow = state

    def read_handoff(self, _project: Project) -> Handoff | None:
        return self.handoff

    def write_handoff(self, _project: Project, handoff: Handoff) -> None:
        self.handoff = handoff

    def delete_handoff(self, _project: Project) -> None:
        self.handoff = None


class FakeProjectLock:
    @contextmanager
    def locked(self, _project: Project):
        yield


class FakeBackend:
    def __init__(self, active_role: Role, output: str) -> None:
        panes = {Role.PM: "%1", Role.DEVELOPER: "%2", Role.REVIEWER: "%3"}
        self.snapshot = SessionSnapshot(
            "atcode-target-1234567890",
            True,
            Layout.PANES,
            tuple(
                RoleEndpoint(
                    role,
                    "team",
                    pane,
                    role is active_role,
                )
                for role, pane in panes.items()
            ),
        )
        self.outputs = {active_role: output}
        self.read_roles: list[Role] = []
        self.deliveries: list[tuple[Role, str]] = []
        self.focused: Role | None = None

    def inspect_session(self, _session_name: str) -> SessionSnapshot:
        return self.snapshot

    def read_role_output(self, _session_name: str, role: Role) -> str:
        self.read_roles.append(role)
        return self.outputs[role]

    def deliver_text(self, _session_name: str, role: Role, text: str) -> None:
        self.deliveries.append((role, text))

    def focus_role(self, _session_name: str, role: Role) -> None:
        self.focused = role


def make_project(tmp_path: Path) -> Project:
    target = tmp_path / "target"
    target.mkdir()
    return Project("target-1234567890", "target", target, "created")


def make_handoff(
    delivery: DeliveryState,
    *,
    transfer_id: int = 1,
) -> Handoff:
    return Handoff(
        transfer_id,
        Role.PM,
        Role.DEVELOPER,
        HandoffDecision.READY,
        delivery,
        "sha256:pending",
        "SUMMARY:\nbuild it",
        "2026-07-15T00:00:00+00:00",
        (
            "2026-07-15T00:00:01+00:00"
            if delivery is DeliveryState.DELIVERED
            else None
        ),
    )


def make_service(
    tmp_path: Path,
    active_role: Role,
    output: str,
    *,
    workflow: WorkflowState | None = None,
) -> tuple[WorkflowService, FakeBackend, MemoryWorkflowStore]:
    project = make_project(tmp_path)
    backend = FakeBackend(active_role, output)
    store = MemoryWorkflowStore(workflow)
    service = WorkflowService(
        project=project,
        session_name=f"atcode-{project.project_id}",
        backend=backend,
        parser=HandoffParser(),
        store=store,
        project_lock=FakeProjectLock(),
        clock=lambda: "2026-07-15T00:00:02+00:00",
    )
    return service, backend, store


def test_pm_handoff_moves_workflow_to_developer(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.PM,
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nbuild it\n</ATCODE_HANDOFF>",
    )

    result = service.next(source_pane="%1")

    assert result.from_role is Role.PM
    assert result.to_role is Role.DEVELOPER
    assert result.transfer_id == 1
    assert store.workflow.status is WorkflowStatus.ACTIVE
    assert store.workflow.current_role is Role.DEVELOPER
    assert store.workflow.round == 1
    assert store.handoff.delivery is DeliveryState.DELIVERED
    assert backend.deliveries[0][0] is Role.DEVELOPER
    assert backend.focused is Role.DEVELOPER


def test_reviewer_approval_completes_at_pm(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.REVIEWER,
        "<ATCODE_HANDOFF>\nSTATUS: approved\nSUMMARY:\nverified\n</ATCODE_HANDOFF>",
        workflow=WorkflowState(
            WorkflowStatus.ACTIVE, Role.REVIEWER, 1, 2, {}, "time"
        ),
    )

    service.next(source_pane="%3")

    assert store.workflow.status is WorkflowStatus.COMPLETE
    assert store.workflow.current_role is Role.PM
    assert backend.focused is Role.PM


def test_reviewer_rejection_then_pm_increments_round(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.REVIEWER,
        "<ATCODE_HANDOFF>\nSTATUS: rejected\nSUMMARY:\nfix test\n</ATCODE_HANDOFF>",
        workflow=WorkflowState(
            WorkflowStatus.ACTIVE, Role.REVIEWER, 1, 2, {}, "time"
        ),
    )
    service.next(source_pane="%3")
    backend.outputs[Role.PM] = (
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nrework\n</ATCODE_HANDOFF>"
    )
    backend.snapshot = SessionSnapshot(
        backend.snapshot.session_name,
        True,
        Layout.PANES,
        tuple(
            RoleEndpoint(item.role, item.window, item.pane, item.role is Role.PM)
            for item in backend.snapshot.endpoints
        ),
    )

    service.next(source_pane="%1")

    assert store.workflow.status is WorkflowStatus.ACTIVE
    assert store.workflow.current_role is Role.DEVELOPER
    assert store.workflow.round == 2
```

- [ ] **Step 2: 실패, 중복, Pending, 복구 테스트 작성**

같은 파일에 다음 테스트를 추가한다.

```python
def test_wrong_source_pane_does_not_capture_or_advance(tmp_path: Path) -> None:
    service, backend, store = make_service(tmp_path, Role.PM, "unused")

    with pytest.raises(AtCodeError, match="WORKFLOW_ROLE_MISMATCH"):
        service.next(source_pane="%2")

    assert backend.read_roles == []
    assert store.workflow == WorkflowState.initial()


def test_duplicate_digest_is_rejected_without_delivery(tmp_path: Path) -> None:
    output = "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nsame\n</ATCODE_HANDOFF>"
    parsed = HandoffParser().parse(output, Role.PM)
    workflow = WorkflowState(
        WorkflowStatus.IDLE,
        Role.PM,
        0,
        1,
        {Role.PM: parsed.digest},
        "time",
    )
    service, backend, _store = make_service(
        tmp_path, Role.PM, output, workflow=workflow
    )

    with pytest.raises(AtCodeError, match="HANDOFF_ALREADY_DELIVERED"):
        service.next(source_pane="%1")

    assert backend.deliveries == []


def test_pending_handoff_is_retried_without_recapture(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path, Role.PM, "must not be read"
    )
    store.handoff = make_handoff(DeliveryState.PENDING)

    service.next(source_pane="%1")

    assert backend.read_roles == []
    assert backend.deliveries[0][0] is Role.DEVELOPER
    assert store.handoff.delivery is DeliveryState.DELIVERED


def test_delivered_handoff_ahead_of_workflow_is_reconciled(
    tmp_path: Path,
) -> None:
    service, _backend, store = make_service(tmp_path, Role.PM, "unused")
    store.handoff = make_handoff(DeliveryState.DELIVERED, transfer_id=1)

    state = service.reconcile()

    assert state.last_transfer_id == 1
    assert state.current_role is Role.DEVELOPER
```

- [ ] **Step 3: Workflow 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_workflow.py`

Expected: `WorkflowService`가 없어 FAIL.

- [ ] **Step 4: TransferResult와 고정 Route 구현**

`src/atcode/domain/models.py`에 다음 결과 타입을 추가한다.

```python
@dataclass(frozen=True)
class TransferResult:
    transfer_id: int
    from_role: Role
    to_role: Role
    workflow_status: WorkflowStatus
    focus_warning: str | None = None
```

`src/atcode/application/workflow.py`에는 Route와 상태 전이 함수를 명시적으로 둔다.

```python
_NEXT_ROLE = {
    Role.PM: Role.DEVELOPER,
    Role.DEVELOPER: Role.REVIEWER,
    Role.REVIEWER: Role.PM,
}


def transition(
    state: WorkflowState,
    source: Role,
    decision: HandoffDecision,
    transfer_id: int,
    digest: str,
    now: str,
) -> WorkflowState:
    digests = dict(state.last_digests)
    digests[source] = digest
    if source is Role.PM:
        round_number = state.round + 1 if state.status is WorkflowStatus.REWORK else 1
        return WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.DEVELOPER,
            round_number,
            transfer_id,
            digests,
            now,
        )
    if source is Role.DEVELOPER:
        return WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.REVIEWER,
            state.round,
            transfer_id,
            digests,
            now,
        )
    status = (
        WorkflowStatus.COMPLETE
        if decision is HandoffDecision.APPROVED
        else WorkflowStatus.REWORK
    )
    return WorkflowState(
        status,
        Role.PM,
        state.round,
        transfer_id,
        digests,
        now,
    )


def reconcile_state(
    state: WorkflowState,
    handoff: Handoff | None,
    now: str,
) -> WorkflowState:
    if (
        handoff is None
        or handoff.delivery is not DeliveryState.DELIVERED
        or handoff.transfer_id <= state.last_transfer_id
    ):
        return state
    return transition(
        state,
        handoff.from_role,
        handoff.decision,
        handoff.transfer_id,
        handoff.digest,
        handoff.delivered_at or now,
    )
```

- [ ] **Step 5: WorkflowService next와 재시도 구현**

`WorkflowService` Constructor는 `project`, `session_name`, `backend`, `parser`, `store`, `project_lock`, `clock`을 받는다. `clock` 기본값은 UTC ISO Timestamp를 반환하는 Callable이다.

`current()`와 `reconcile()`은 Project Lock 안에서 Store를 읽고 `reconcile_state()` 결과가 달라졌을 때만 Workflow를 다시 쓴다. `next()`는 Lock 안에서 같은 Reconcile, Session Endpoint 확인, Source Role 확인, Pending 우선 재시도, Capture/Parse/Digest 검증, Pending 저장, Transfer Envelope 전달, Delivered 저장, Workflow 전이 저장 순서로 실행한다. Envelope는 다음 함수로 만든다.

```python
def transfer_text(handoff: Handoff) -> str:
    return (
        f"[ATCODE_TRANSFER id={handoff.transfer_id} "
        f"from={handoff.from_role.value} to={handoff.to_role.value}]\n"
        f"{handoff.body}"
    )
```

Pending 재시도는 저장된 `transfer_id`, 대상 역할, 본문을 그대로 사용한다. Backend 호출 성공 직후 Process가 중단되면 동일 Transfer가 다시 입력될 수 있으므로 Exactly Once를 주장하지 않는다. Task 7의 Prompt 중복 규칙이 같은 Transfer ID의 반복 작업을 막는 보조 장치다.

Focus는 Workflow 저장 후 실행한다. Focus `AtCodeError`는 `focus_warning`에 담고 전달 상태를 되돌리지 않는다. `reset()`은 `WorkflowState.initial()`을 쓰고 Handoff를 삭제한다.

- [ ] **Step 6: Workflow 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_workflow.py tests/unit/test_handoffs.py tests/unit/test_workflow_store.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/domain/models.py src/atcode/application/workflow.py tests/unit/test_workflow.py
git commit -m "feat: coordinate fixed role relay workflow"
```

### Task 7: 역할별 Handoff 출력 계약

**Files:**
- Modify: `prompts/pm.md`
- Modify: `prompts/developer.md`
- Modify: `prompts/reviewer.md`
- Modify: `tests/unit/test_prompts.py`

**Interfaces:**
- Produces: Model-neutral `<ATCODE_HANDOFF>` 출력 계약
- Produces: 중복 `ATCODE_TRANSFER id` 처리 규칙
- Consumes: Task 2의 역할별 Status 허용 규칙

- [ ] **Step 1: Prompt 계약 실패 테스트 작성**

`tests/unit/test_prompts.py`에 다음 테스트를 추가하고 기존 `Phase 1` 고정 Assertion은 `AtCode Runtime` 표현으로 바꾼다.

```python
def test_role_templates_define_handoff_protocol() -> None:
    templates = {
        role: (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(
            encoding="utf-8"
        )
        for role in Role
    }

    for text in templates.values():
        assert "<ATCODE_HANDOFF>" in text
        assert "</ATCODE_HANDOFF>" in text
        assert "ATCODE_TRANSFER" in text
        assert "중복" in text
        assert "대기" in text

    assert "STATUS: ready" in templates[Role.PM]
    assert "STATUS: ready" in templates[Role.DEVELOPER]
    assert "STATUS: approved" in templates[Role.REVIEWER]
    assert "STATUS: rejected" in templates[Role.REVIEWER]


def test_waiting_role_must_not_emit_handoff() -> None:
    for role in Role:
        text = (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(
            encoding="utf-8"
        )
        assert "waiting" in text
        assert "인계 영역을 출력하지 않는다" in text
```

- [ ] **Step 2: Prompt 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_prompts.py`

Expected: Handoff Protocol 문구가 없어 FAIL.

- [ ] **Step 3: PM과 Developer 계약 추가**

PM Prompt의 산출물 끝에 다음 계약을 추가한다.

```text
## AtCode 인계

- 시작 Prompt의 실행 모드가 `waiting`이면 새 인계를 받을 때까지 프로젝트 조사, 파일 변경, 역할 작업을 시작하지 않고 인계 영역을 출력하지 않는다.
- 동일한 `[ATCODE_TRANSFER id=N]`을 이미 처리했다면 작업을 반복하지 않고 중복임을 짧게 알린다.
- Developer에게 전달할 준비가 끝났을 때만 응답 마지막에 다음 형식을 정확히 한 번 출력한다.

<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
- 요구사항
- 범위와 제외 범위
- 완료 조건
- Developer 작업과 검증 명령
</ATCODE_HANDOFF>
```

Developer Prompt에는 같은 waiting/중복 규칙과 함께 다음 출력 형식을 추가한다.

```text
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
- 구현한 내용
- 변경 파일
- 실행한 검증과 실제 결과
- Reviewer가 확인할 완료 조건과 남은 위험
</ATCODE_HANDOFF>
```

- [ ] **Step 4: Reviewer 계약 추가**

Reviewer Prompt에는 승인과 반려를 명시한다.

```text
<ATCODE_HANDOFF>
STATUS: approved
SUMMARY:
- 검토 범위
- 실행한 테스트와 실제 결과
- 완료 조건 충족 근거
- 남은 위험 또는 미검증 항목
</ATCODE_HANDOFF>
```

중요 결함이나 검증 실패가 있으면 `STATUS: rejected`를 사용하고 재현 명령, 실제 결과, Developer 재작업 조건을 SUMMARY에 포함한다. Waiting과 중복 Transfer 규칙은 다른 역할과 동일하게 둔다.

- [ ] **Step 5: Prompt 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_prompts.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add prompts/pm.md prompts/developer.md prompts/reviewer.md tests/unit/test_prompts.py
git commit -m "feat: define model neutral handoff prompts"
```

### Task 8: Active/Waiting 시작 Prompt와 Session 재개

**Files:**
- Modify: `src/atcode/application/prompts.py`
- Modify: `src/atcode/application/sessions.py`
- Modify: `src/atcode/bootstrap.py`
- Modify: `src/atcode/ports/storage.py`
- Modify: `src/atcode/infrastructure/storage/state.py`
- Modify: `tests/unit/test_prompts.py`
- Modify: `tests/unit/test_sessions.py`

**Interfaces:**
- Produces: `StartupPromptBuilder.build(rendered, role, workflow, handoff)`
- Consumes: Task 3의 Workflow Store와 Project Lock
- Consumes: Task 4의 Layout SessionSpec
- Consumes: Task 6의 `reconcile_state()` Pure Function

- [ ] **Step 1: 시작 Prompt 실패 테스트 작성**

`tests/unit/test_prompts.py`에 다음 테스트를 추가한다.

```python
from atcode.application.prompts import StartupPromptBuilder
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    WorkflowState,
    WorkflowStatus,
)


def test_idle_startup_marks_only_pm_active(tmp_path: Path) -> None:
    rendered = RenderedPrompt("role contract", tmp_path / "developer.md")
    startup = StartupPromptBuilder()

    text = startup.build(
        rendered, Role.DEVELOPER, WorkflowState.initial(), None
    ).text

    assert "MODE: waiting" in text
    assert "[ATCODE_TRANSFER id=" not in text
    assert rendered.text == "role contract"


def test_resume_includes_handoff_only_for_current_role(tmp_path: Path) -> None:
    workflow = WorkflowState(
        WorkflowStatus.ACTIVE, Role.DEVELOPER, 1, 1, {}, "time"
    )
    handoff = Handoff(
        1,
        Role.PM,
        Role.DEVELOPER,
        HandoffDecision.READY,
        DeliveryState.DELIVERED,
        "sha256:abc",
        "SUMMARY:\nbuild it",
        "created",
        "delivered",
    )
    rendered = RenderedPrompt("role contract", tmp_path / "developer.md")
    startup = StartupPromptBuilder()

    developer = startup.build(rendered, Role.DEVELOPER, workflow, handoff)
    reviewer = startup.build(rendered, Role.REVIEWER, workflow, handoff)

    assert "MODE: active" in developer.text
    assert "[ATCODE_TRANSFER id=1 from=pm to=developer]" in developer.text
    assert "MODE: waiting" in reviewer.text
    assert "build it" not in reviewer.text
    assert developer.path == rendered.path
```

- [ ] **Step 2: Session 재개 실패 테스트 작성**

`tests/unit/test_sessions.py` Fake Workflow Store를 추가하고 다음을 검증한다.

```python
class FakeWorkflowStore:
    def __init__(self) -> None:
        self.workflow = WorkflowState.initial()
        self.handoff: Handoff | None = None

    def read_workflow(self, _project):
        return self.workflow

    def write_workflow(self, _project, state):
        self.workflow = state

    def read_handoff(self, _project):
        return self.handoff

    def write_handoff(self, _project, handoff):
        self.handoff = handoff

    def delete_handoff(self, _project):
        self.handoff = None


def runtime_handoff(delivery: DeliveryState) -> Handoff:
    return Handoff(
        1,
        Role.PM,
        Role.DEVELOPER,
        HandoffDecision.READY,
        delivery,
        "sha256:abc",
        "SUMMARY:\nbuild it",
        "created",
        "delivered" if delivery is DeliveryState.DELIVERED else None,
    )


def test_restart_launches_only_current_role_with_latest_handoff(tmp_path: Path) -> None:
    service, backend, _state_store, workflow_store = make_service(tmp_path)
    workflow_store.workflow = WorkflowState(
        WorkflowStatus.ACTIVE, Role.DEVELOPER, 1, 1, {}, "time"
    )
    workflow_store.handoff = runtime_handoff(DeliveryState.DELIVERED)

    service.start()

    prompts = {
        spec.role: spec.launch.arguments[0]
        for spec in backend.created_specs[0].roles
    }
    assert "MODE: active" in prompts[Role.DEVELOPER]
    assert "build it" in prompts[Role.DEVELOPER]
    assert "MODE: waiting" in prompts[Role.PM]
    assert "build it" not in prompts[Role.PM]
    assert "MODE: waiting" in prompts[Role.REVIEWER]


def test_pending_handoff_keeps_source_active_without_target_injection(
    tmp_path: Path,
) -> None:
    service, backend, _state_store, workflow_store = make_service(tmp_path)
    workflow_store.handoff = runtime_handoff(DeliveryState.PENDING)

    service.start()

    prompts = {
        spec.role: spec.launch.arguments[0]
        for spec in backend.created_specs[0].roles
    }
    assert "MODE: active" in prompts[Role.PM]
    assert "MODE: waiting" in prompts[Role.DEVELOPER]
    assert "build it" not in prompts[Role.DEVELOPER]
```

`make_service()`는 `FakeWorkflowStore`를 만들고 `SessionService`에 `workflow_store`, `FakeProjectLock`, `StartupPromptBuilder`를 주입한 뒤 네 번째 반환값으로 Store를 돌려준다. 기존 Test의 세 변수 Unpack은 네 번째 값을 `_workflow_store`로 받도록 모두 갱신한다.

- [ ] **Step 3: Prompt와 Session 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_prompts.py tests/unit/test_sessions.py`

Expected: `StartupPromptBuilder`와 Workflow Store 의존성이 없어 FAIL.

- [ ] **Step 4: StartupPromptBuilder 구현**

`src/atcode/application/prompts.py`에 다음 Class를 추가한다.

```python
class StartupPromptBuilder:
    def build(
        self,
        rendered: RenderedPrompt,
        role: Role,
        workflow: WorkflowState,
        handoff: Handoff | None,
    ) -> RenderedPrompt:
        active = role is workflow.current_role
        sections = [rendered.text.rstrip(), "", f"ATCODE RUNTIME MODE: {'active' if active else 'waiting'}"]
        if not active:
            sections.append(
                "새 ATCODE_TRANSFER를 받기 전에는 역할 작업을 시작하지 마세요."
            )
        elif (
            handoff is not None
            and handoff.delivery is DeliveryState.DELIVERED
            and handoff.to_role is role
        ):
            sections.extend(
                [
                    "",
                    f"[ATCODE_TRANSFER id={handoff.transfer_id} "
                    f"from={handoff.from_role.value} to={handoff.to_role.value}]",
                    handoff.body,
                ]
            )
        return RenderedPrompt("\n".join(sections).rstrip() + "\n", rendered.path)
```

- [ ] **Step 5: SessionService에 Workflow Context 조합**

`SessionService` Constructor에 `workflow_store`, `project_lock`, `startup_prompts`를 추가한다. `start()`의 기존 `state_store.locked()`를 `project_lock.locked()`로 교체한다. 새 Session을 만들기 전에 같은 Lock 안에서 Workflow와 Handoff를 읽고 Task 6의 Pure Reconcile Function으로 정합성을 맞춘 뒤 각 Role의 Rendered Prompt를 `StartupPromptBuilder`에 통과시킨다.

모든 SessionService 호출이 `ProjectLock`으로 전환된 뒤 `StateStore` Protocol과 `JsonStateStore`에서 `locked()` 및 OS Lock Helper를 제거한다. Lock 구현은 `JsonProjectLock` 한 곳에만 남긴다.

SessionSpec은 `SessionSpec(session_name, project.root, config.layout, tuple(role_specs))`로 만들고 Runtime State에는 `config.layout`과 역할별 논리 Endpoint를 기록한다. 기존 Session의 Layout이 Config와 다르면 `SESSION_DEGRADED` Hint로 `atcode stop`, `atcode start`를 안내한다.

RoleRuntime의 논리 Endpoint는 `RoleRuntime(role, adapter, role.value)`로 기록한다. Next Binding 설치는 CLI 시작 흐름과 함께 Task 9에서 연결해 SessionService가 사용자 입력 장치를 알지 않게 유지한다.

`src/atcode/bootstrap.py`는 `JsonProjectLock`, `JsonWorkflowStore`, `StartupPromptBuilder`를 한 번 생성해 `AppContainer` Field로 보관하고 `sessions()`에서 새 SessionService 인자로 전달한다. 이 Task가 끝난 시점에도 기존 CLI Lifecycle 전체가 실행 가능해야 한다.

- [ ] **Step 6: Prompt와 Session 테스트 통과 확인**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/atcode/application/prompts.py src/atcode/application/sessions.py src/atcode/bootstrap.py src/atcode/ports/storage.py src/atcode/infrastructure/storage/state.py tests/unit/test_prompts.py tests/unit/test_sessions.py
git commit -m "feat: restore active role startup context"
```

### Task 9: Container와 CLI의 next, status, start --fresh

**Files:**
- Modify: `src/atcode/bootstrap.py`
- Modify: `src/atcode/cli.py`
- Modify: `tests/integration/test_cli.py`
- Modify: `tests/integration/test_no_target_artifacts.py`

**Interfaces:**
- Produces: `AppContainer.workflows(project)`
- Produces: public `atcode next`, `atcode start --fresh`
- Produces: internal `next --session --pane --notify`
- Produces: status의 Workflow 상태 출력

- [ ] **Step 1: CLI Relay와 상태 출력 실패 테스트 작성**

`tests/integration/test_cli.py` FakeBackend에 Role Output, Delivery, Focus Method를 추가하고 다음 테스트를 작성한다.

```python
def test_next_routes_current_role_and_prints_transfer(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")
    container.backend.outputs[Role.PM] = (
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nbuild it\n</ATCODE_HANDOFF>"
    )

    code, stdout, stderr = invoke(container, target, "next")

    assert code == 0
    assert "pm -> developer" in stdout
    assert "transfer=1" in stdout
    assert stderr == ""


def test_status_prints_workflow_role_and_round(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")

    code, stdout, _stderr = invoke(container, target, "status")

    assert code == 0
    assert "workflow=idle" in stdout
    assert "role=pm" in stdout
    assert "round=0" in stdout


def test_internal_next_rejects_unknown_session_without_traceback(tmp_path: Path) -> None:
    container = make_container(tmp_path)

    code, _stdout, stderr = invoke(
        container,
        tmp_path,
        "next",
        "--session",
        "atcode-unknown-1234567890",
        "--pane",
        "%1",
    )

    assert code == 1
    assert "SESSION_NOT_REGISTERED" in stderr
    assert "Traceback" not in stderr
```

- [ ] **Step 2: Fresh 확인 실패 테스트 작성**

Integration `invoke()`에 `stdin=StringIO`를 추가하고 다음 테스트를 작성한다.

```python
def test_start_fresh_requires_stopped_session_and_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")

    running_code, _out, running_error = invoke(
        container, target, "start", "--fresh", stdin_text="y\n"
    )
    assert running_code == 1
    assert "FRESH_REQUIRES_STOPPED_SESSION" in running_error

    invoke(container, target, "stop")
    cancelled_code, _out, _error = invoke(
        container, target, "start", "--fresh", stdin_text="n\n"
    )
    assert cancelled_code == 1


def test_start_fresh_resets_workflow_after_yes(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    project = container.registered_project(None, target)
    container.workflow_store.write_workflow(
        project,
        WorkflowState(WorkflowStatus.REWORK, Role.PM, 2, 4, {}, "time"),
    )

    code, stdout, stderr = invoke(
        container, target, "start", "--fresh", stdin_text="y\n"
    )

    assert code == 0
    assert "초기화" in stdout
    assert stderr == ""
    assert container.workflows(project).current().status is WorkflowStatus.IDLE
```

- [ ] **Step 3: CLI Integration 테스트 실패 확인**

Run: `python -m pytest -q tests/integration/test_cli.py tests/integration/test_no_target_artifacts.py`

Expected: next Parser, Container Workflow 조립, fresh 인자가 없어 FAIL.

- [ ] **Step 4: AppContainer 조립 구현**

`RuntimePaths`는 기존 `projects` Root를 재사용한다. Task 8에서 조립한 `JsonProjectLock`, `JsonWorkflowStore`, `StartupPromptBuilder`를 재사용하고 `build_container()`에 `HandoffParser`를 추가한다.

```python
def workflows(self, project: Project) -> WorkflowService:
    return WorkflowService(
        project=project,
        session_name=f"atcode-{project.project_id}",
        backend=self.backend,
        parser=self.handoff_parser,
        store=self.workflow_store,
        project_lock=self.project_lock,
    )
```

`sessions()`에도 같은 `workflow_store`, `project_lock`, `startup_prompts`를 전달한다. `project_for_session(session_name)`은 Project Store의 등록 Project를 순회해 `f"atcode-{project.project_id}" == session_name`인 정확한 Project만 반환하고 없으면 `SESSION_NOT_REGISTERED`를 발생시킨다.

Integration FakeBackend에는 `install_next_action()`, `next_action_probe()`, `display_message()`를 추가한다. 기본 Binding 결과는 `DiagnosticResult("next binding", DiagnosticLevel.PASS, "Ctrl+b Enter")`다.

- [ ] **Step 5: CLI Parser와 출력 구현**

`start` Parser에 `--fresh`를 추가하고 `next` Parser에는 `--project`, 숨김 `--session`, `--pane`, `--notify`를 추가한다. `run()` Signature에 `stdin: TextIO`를 추가하고 `main()`은 `sys.stdin`을 전달한다.

일반 `next`는 등록 Project의 Workflow Service를 사용하고 내부 Session 호출은 `project_for_session()`으로 Project를 찾는다. 성공 출력은 다음 형식을 사용한다.

```text
transfer=1 pm -> developer workflow=active
```

`--notify`면 같은 문구 또는 구조화된 Error 문구를 `backend.display_message()`로 표시한다.

`status`는 기존 Session Line 다음에 다음 형식을 출력한다.

```text
workflow=idle role=pm round=0 transfer=0 delivery=none
```

`start`는 Session 시작 전에 `backend.install_next_action()`을 호출한다. 결과가 WARN이면 Session 생성은 계속하고 `WARNING next binding: <message>`와 `Hint: Use atcode next.`를 출력하되 Exit Code는 0으로 유지한다. 설치 자체가 실패해도 Shell의 `atcode next`가 가능하면 같은 WARN 복구 경로를 사용한다.

`start --fresh`는 Session이 존재하면 `FRESH_REQUIRES_STOPPED_SESSION`을 반환한다. Workflow/Handoff가 있으면 프로젝트 ID와 상태를 출력하고 `[y/N]`에서 정확히 `y` 또는 `yes`일 때만 `WorkflowService.reset()` 후 Session을 시작한다.

- [ ] **Step 6: 대상 프로젝트 무흔적 Workflow Cycle 추가**

`tests/integration/test_no_target_artifacts.py`의 Lifecycle에 PM → Developer → Reviewer → PM next Cycle을 추가한다. FakeBackend Output을 역할별 Handoff로 바꾸면서 각 `next` 전후 `snapshot(target)`이 최초와 같음을 검증한다.

- [ ] **Step 7: CLI Integration 테스트 통과 확인**

Run: `python -m pytest -q tests/integration/test_cli.py tests/integration/test_no_target_artifacts.py`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/atcode/bootstrap.py src/atcode/cli.py tests/integration/test_cli.py tests/integration/test_no_target_artifacts.py
git commit -m "feat: expose relay workflow commands"
```

### Task 10: Diagnostics, 사용자 문서, 전체 회귀 검증

**Files:**
- Modify: `src/atcode/application/diagnostics.py`
- Modify: `src/atcode/bootstrap.py`
- Modify: `tests/unit/test_diagnostics.py`
- Modify: `README.md`
- Modify: `tests/integration/test_cli.py`

**Interfaces:**
- Produces: doctor의 Workflow/Handoff/Role Endpoint/Binding 진단
- Produces: 비개발자용 3-Pane과 Relay 사용 설명
- Consumes: Task 5의 `next_action_probe()`와 Task 3 Store

- [ ] **Step 1: Diagnostics 실패 테스트 작성**

`tests/unit/test_diagnostics.py` FakeBackend와 Container Dependency를 확장하고 다음 테스트를 추가한다.

```python
from contextlib import contextmanager

from atcode.domain.models import Layout, RoleEndpoint, WorkflowState


class FakeBackend:
    def __init__(
        self,
        snapshot: SessionSnapshot,
        next_action: DiagnosticResult | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.next_action = next_action or DiagnosticResult(
            "next binding", DiagnosticLevel.PASS, "Ctrl+b Enter"
        )

    def probe(self):
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, "available")

    def inspect_session(self, _name):
        return self.snapshot

    def next_action_probe(self):
        return self.next_action


class FakeWorkflowStore:
    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid

    def read_workflow(self, _project):
        if self.invalid:
            raise AtCodeError("WORKFLOW_INVALID", "broken workflow", hint="repair it")
        return WorkflowState.initial()

    def read_handoff(self, _project):
        return None


class FakeProjectLock:
    @contextmanager
    def locked(self, _project):
        yield


def make_service(
    tmp_path: Path,
    *,
    configuration=None,
    prompts=None,
    snapshot=None,
    state=None,
    next_action=None,
    workflow_invalid: bool = False,
) -> DiagnosticsService:
    home = tmp_path / "runtime"
    return DiagnosticsService(
        paths=RuntimePaths(home, home / "projects", home / "config.json"),
        configuration=configuration or FakeConfiguration(),
        adapters=FakeAdapters(),
        backend=FakeBackend(
            snapshot or SessionSnapshot.stopped("session"), next_action
        ),
        prompts=prompts or FakePrompts(),
        state_store=FakeStateStore(state),
        workflow_store=FakeWorkflowStore(invalid=workflow_invalid),
        project_lock=FakeProjectLock(),
    )


def running_panes_snapshot() -> SessionSnapshot:
    return SessionSnapshot(
        "atcode-target-1234567890",
        True,
        Layout.PANES,
        tuple(
            RoleEndpoint(
                role,
                "team",
                {Role.PM: "%1", Role.DEVELOPER: "%2", Role.REVIEWER: "%3"}[role],
                role is Role.PM,
            )
            for role in Role
        ),
    )


def test_doctor_reports_role_endpoints_and_next_binding(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service = make_service(
        tmp_path,
        snapshot=running_panes_snapshot(),
        next_action=DiagnosticResult(
            "next binding", DiagnosticLevel.PASS, "Ctrl+b Enter"
        ),
    )

    results = service.run(project)

    by_name = {result.name: result for result in results}
    assert by_name["state/session"].level is DiagnosticLevel.PASS
    assert "pm, developer, reviewer" in by_name["state/session"].message
    assert by_name["next binding"].level is DiagnosticLevel.PASS


def test_doctor_warns_when_enter_binding_conflicts(tmp_path: Path) -> None:
    service = make_service(
        tmp_path,
        next_action=DiagnosticResult(
            "next binding",
            DiagnosticLevel.WARN,
            "Ctrl+b Enter is already bound.",
            hint="Use atcode next.",
        ),
    )

    results = service.run(None)

    binding = next(result for result in results if result.name == "next binding")
    assert binding.level is DiagnosticLevel.WARN
    assert binding.hint == "Use atcode next."


def test_doctor_fails_for_inconsistent_workflow_and_handoff(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service = make_service(tmp_path, workflow_invalid=True)

    results = service.run(project)

    workflow = next(result for result in results if result.name == "workflow")
    assert workflow.level is DiagnosticLevel.FAIL
    assert "repair" in workflow.hint.lower()
```

- [ ] **Step 2: Diagnostics 테스트 실패 확인**

Run: `python -m pytest -q tests/unit/test_diagnostics.py`

Expected: Workflow와 Binding 진단이 없어 FAIL.

- [ ] **Step 3: Diagnostics 구현**

`DiagnosticsService`에 `workflow_store`와 `project_lock`을 주입한다. Project가 있으면 Lock 안에서 Workflow와 Handoff를 읽고 Task 6 Reconcile 규칙으로 모순을 판정한다. 다음 Result를 추가한다.

```text
PASS workflow: idle; role=pm; round=0; transfer=0
WARN next binding: Ctrl+b Enter is already bound.
```

Session 진단은 Window 이름이 아니라 `SessionSnapshot.endpoints`의 Role 집합과 Layout을 사용한다. Backend `next_action_probe()`가 FAIL이면 doctor Exit Code 1, WARN이면 기존처럼 Exit Code 0을 유지한다.

`src/atcode/bootstrap.py`의 DiagnosticsService 생성에도 기존 `workflow_store`와 `project_lock`을 전달한다.

- [ ] **Step 4: README를 실제 사용자 흐름으로 갱신**

README의 Phase 2 방향 문구를 구현된 사용법으로 바꾼다. 정상 사용은 다음 네 줄을 중심으로 설명한다.

```bash
cd /path/to/project
atcode start
atcode attach
# 역할 작업 완료 후 Ctrl+b Enter
```

다음 내용도 포함한다.

- 기본 3-Pane의 역할 Label과 `Ctrl+b z`
- `Ctrl+b Enter`의 PM → Developer → Reviewer → PM 흐름
- 단축키 충돌 시 `atcode next`
- 재부팅 후 `atcode start` 자동 재개
- 오래된 작업 폐기 절차 `atcode stop`, `atcode start --fresh`
- windows Layout 설정과 적용을 위한 stop/start
- Prompt는 역할 계약, handoff.json은 최신 인계 하나라는 설명
- 전체 대화와 Task Queue는 저장하지 않는다는 제한
- 모든 Runtime 파일은 `ATCODE_HOME`에 있고 대상 프로젝트에는 관리 흔적이 없다는 원칙

- [ ] **Step 5: CLI doctor Integration Assertion 추가**

`tests/integration/test_cli.py`의 doctor 성공 Test에서 `workflow`, `next binding`, Role Endpoint 문구가 출력되고 Traceback이 없음을 확인한다. Binding WARN만 있는 경우 Exit Code 0인지도 검증한다.

- [ ] **Step 6: Diagnostics와 Integration 테스트 통과 확인**

Run: `python -m pytest -q tests/unit/test_diagnostics.py tests/integration/test_cli.py`

Expected: PASS.

- [ ] **Step 7: 전체 자동 검증 실행**

Run:

```bash
python -m pytest -q
python -m compileall -q src tests
bash -n bin/atcode scripts/install.sh scripts/uninstall.sh
```

Expected: 모든 pytest PASS, compileall과 Bash Syntax Exit Code 0.

- [ ] **Step 8: 금지 범위와 대상 프로젝트 무흔적 확인**

Run:

```bash
rg -n "sqlite|sqlalchemy|websocket|fastapi|capture.*write|handoffs/" src tests README.md
python -m pytest -q tests/integration/test_no_target_artifacts.py
```

Expected: 새 Database/Web/전체 Capture 저장/Handoff 이력 구현 Match 없음, 무흔적 Test PASS. `capture-pane` 자체와 `handoff.json` Match는 허용하되 Capture 전체를 파일에 쓰는 경로는 없어야 한다.

- [ ] **Step 9: Commit**

```bash
git add src/atcode/application/diagnostics.py src/atcode/bootstrap.py tests/unit/test_diagnostics.py tests/integration/test_cli.py README.md
git commit -m "feat: add relay diagnostics and docs"
```

- [ ] **Step 10: WSL 수동 인수 검증**

WSL의 실제 테스트 프로젝트에서 다음을 실행한다.

```bash
atcode stop
atcode start
atcode attach
```

확인 항목:

1. `team` Window에 PM, Developer, Reviewer Label이 있는 세 Pane이 보인다.
2. PM에게 작은 작업을 지시하고 PM Handoff가 출력된 뒤 `Ctrl+b Enter`를 누르면 Developer에 Transfer ID와 본문이 입력되고 Developer Pane이 선택된다.
3. Developer와 Reviewer에서도 같은 방식으로 진행된다.
4. Reviewer `approved`가 PM으로 전달된 뒤 `atcode status`가 `workflow=complete role=pm`을 표시한다.
5. Reviewer `rejected` 시 PM을 거쳐 Developer로 돌아가며 Round가 증가한다.
6. `Ctrl+b z`가 선택 Pane을 확대하고 다시 원복한다.
7. `atcode stop`, `atcode start` 후 최신 역할과 Handoff가 복구된다.
8. `layout windows`로 stop/start한 뒤에도 같은 Relay가 동작한다.
9. 대상 프로젝트에는 AtCode 관리 파일이 생기지 않는다.

수동 검증에서 실패하면 해당 실패를 재현하는 자동 Test를 먼저 추가하고 최소 수정 후 전체 검증을 다시 실행한다.

---

## Final Review Checklist

- [ ] 모든 Commit이 하나의 논리 변경만 포함한다.
- [ ] `git status --short`가 비어 있다.
- [ ] Runtime State v1과 Configuration v1 호환 Test가 통과한다.
- [ ] Workflow/Handoff 손상과 Pending 재시도가 구조화된 오류를 반환한다.
- [ ] 사용자 Handoff 문자열이 Shell Command에 포함되지 않는다.
- [ ] 기본 3-Pane과 선택 3-Window가 같은 WorkflowService를 사용한다.
- [ ] Prompt 파일에 Handoff가 누적되지 않는다.
- [ ] `handoff.json` 외 Handoff 이력 파일이 없다.
- [ ] 대상 프로젝트 무흔적 Test가 통과한다.
- [ ] README 명령이 WSL 수동 검증에서 실제로 동작한다.
