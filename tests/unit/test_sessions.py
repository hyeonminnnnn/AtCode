from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from atcode.application.sessions import SessionService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    DeliveryState,
    Handoff,
    HandoffDecision,
    Layout,
    LaunchSpec,
    Lifecycle,
    Project,
    RenderedPrompt,
    Role,
    RoleAssignment,
    RoleEndpoint,
    RuntimeConfig,
    SessionSnapshot,
    WorkflowState,
    WorkflowStatus,
)
from atcode.application.prompts import StartupPromptBuilder


class FakeConfig:
    def effective(self, _project):
        return RuntimeConfig(
            "tmux",
            {role: RoleAssignment("codex") for role in Role},
            Layout.PANES,
        )


class FakePromptRenderer:
    def __init__(self, root: Path) -> None:
        self.root = root

    def render(self, project, role):
        path = self.root / f"{role.value}.md"
        return RenderedPrompt(f"{role.value} prompt", path)


class FakeAdapter:
    name = "codex"

    def __init__(self, available: bool = True) -> None:
        self.available = available

    def probe(self):
        level = DiagnosticLevel.PASS if self.available else DiagnosticLevel.FAIL
        return DiagnosticResult(self.name, level, "probe")

    def build_launch(self, context):
        return LaunchSpec("codex", (context.prompt.text,), {})


class FakeRegistry:
    def __init__(self, adapter: FakeAdapter) -> None:
        self.adapter = adapter

    def get(self, _name):
        return self.adapter


class FakeBackend:
    def __init__(self) -> None:
        self.snapshot = SessionSnapshot.stopped("atcode-target-1234567890")
        self.created_specs = []
        self.terminated = []

    def probe(self):
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, "tmux 3")

    def inspect_session(self, _name):
        return self.snapshot

    def create_session(self, spec):
        self.created_specs.append(spec)
        endpoints = tuple(
            RoleEndpoint(role_spec.role, "team", f"%{index}", index == 1)
            for index, role_spec in enumerate(spec.roles, start=1)
        )
        self.snapshot = SessionSnapshot(
            spec.session_name,
            True,
            spec.layout,
            endpoints,
        )

    def terminate_session(self, name):
        self.terminated.append(name)
        self.snapshot = SessionSnapshot.stopped(name)

    def attach_session(self, _name):
        return None


class FakeStateStore:
    def __init__(self) -> None:
        self.states = []
        self.lock_count = 0

    def write(self, _project, state):
        self.states.append(state)

    def read(self, _project):
        return self.states[-1] if self.states else None


class FakeProjectLock:
    def __init__(self, state_store: FakeStateStore) -> None:
        self._state_store = state_store

    @contextmanager
    def locked(self, _project):
        self._state_store.lock_count += 1
        yield


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


def make_service(tmp_path: Path, *, adapter_available: bool = True):
    target = tmp_path / "target"
    target.mkdir()
    project = Project(
        "target-1234567890",
        "target",
        target,
        "2026-07-15T00:00:00Z",
    )
    backend = FakeBackend()
    state_store = FakeStateStore()
    workflow_store = FakeWorkflowStore()
    service = SessionService(
        project=project,
        configuration=FakeConfig(),
        prompts=FakePromptRenderer(tmp_path / "runtime"),
        adapters=FakeRegistry(FakeAdapter(adapter_available)),
        backend=backend,
        state_store=state_store,
        workflow_store=workflow_store,
        project_lock=FakeProjectLock(state_store),
        startup_prompts=StartupPromptBuilder(),
        atcode_home=tmp_path / "runtime",
    )
    return service, backend, state_store, workflow_store


def test_start_preflights_all_adapters_before_backend_create(tmp_path: Path) -> None:
    service, backend, _state_store, _workflow_store = make_service(
        tmp_path,
        adapter_available=False,
    )

    with pytest.raises(AtCodeError, match="ADAPTER_NOT_FOUND"):
        service.start()

    assert backend.created_specs == []


def test_start_creates_three_role_endpoints_and_persists_running_state(
    tmp_path: Path,
) -> None:
    service, backend, state_store, _workflow_store = make_service(tmp_path)

    state = service.start()

    assert state.status is Lifecycle.RUNNING
    assert tuple(role.role for role in backend.created_specs[0].roles) == (
        Role.PM,
        Role.DEVELOPER,
        Role.REVIEWER,
    )
    assert tuple(role.role.value for role in backend.created_specs[0].roles) == (
        "pm",
        "developer",
        "reviewer",
    )
    assert backend.created_specs[0].layout is Layout.PANES
    assert state_store.states[-1] == state


def test_start_is_idempotent_when_session_already_exists(tmp_path: Path) -> None:
    service, backend, _state_store, _workflow_store = make_service(tmp_path)
    service.start()

    state = service.start()

    assert state.status is Lifecycle.RUNNING
    assert len(backend.created_specs) == 1


def test_start_rejects_an_existing_legacy_session(tmp_path: Path) -> None:
    service, backend, state_store, _workflow_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        None,
        (),
    )

    with pytest.raises(AtCodeError, match="SESSION_DEGRADED"):
        service.start()

    assert state_store.states[-1].status is Lifecycle.DEGRADED
    assert backend.created_specs == []


def test_stop_is_idempotent(tmp_path: Path) -> None:
    service, backend, _state_store, _workflow_store = make_service(tmp_path)

    state = service.stop()

    assert state.status is Lifecycle.STOPPED
    assert backend.terminated == []


def test_repeated_stop_preserves_the_original_stop_timestamp(tmp_path: Path) -> None:
    service, _backend, _state_store, _workflow_store = make_service(tmp_path)
    service.start()

    first = service.stop()
    second = service.stop()

    assert first.stopped_at is not None
    assert second.stopped_at == first.stopped_at


def test_status_is_degraded_when_role_window_is_missing(tmp_path: Path) -> None:
    service, backend, _state_store, _workflow_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        Layout.PANES,
        (
            RoleEndpoint(Role.PM, "team", "%1", True),
            RoleEndpoint(Role.DEVELOPER, "team", "%2"),
        ),
    )

    state = service.status()

    assert state.status is Lifecycle.DEGRADED


def test_status_is_degraded_when_legacy_windows_are_extra(tmp_path: Path) -> None:
    service, backend, _state_store, _workflow_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        None,
        tuple(
            RoleEndpoint(role, role.value, f"%{index}", index == 1)
            for index, role in enumerate(Role, start=1)
        ),
    )

    state = service.status()

    assert state.status is Lifecycle.DEGRADED


def test_status_updates_state_while_holding_project_lock(tmp_path: Path) -> None:
    service, _backend, state_store, _workflow_store = make_service(tmp_path)

    service.status()

    assert state_store.lock_count == 1


def test_status_preserves_stopped_timestamp(tmp_path: Path) -> None:
    service, _backend, _state_store, _workflow_store = make_service(tmp_path)
    stopped = service.stop()

    current = service.status()

    assert stopped.stopped_at is not None
    assert current.stopped_at == stopped.stopped_at


def test_restart_launches_only_current_role_with_latest_handoff(
    tmp_path: Path,
) -> None:
    service, backend, _state_store, workflow_store = make_service(tmp_path)
    workflow_store.workflow = WorkflowState(
        WorkflowStatus.ACTIVE,
        Role.DEVELOPER,
        1,
        1,
        {},
        "time",
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
