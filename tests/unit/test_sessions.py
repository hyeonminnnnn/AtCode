from __future__ import annotations

from pathlib import Path

import pytest

from atcode.application.sessions import SessionService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    LaunchSpec,
    Lifecycle,
    Project,
    RenderedPrompt,
    Role,
    RoleAssignment,
    RuntimeConfig,
    SessionSnapshot,
)


class FakeConfig:
    def effective(self, _project):
        return RuntimeConfig(
            "tmux",
            {role: RoleAssignment("codex") for role in Role},
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
        windows = tuple(window.name for window in spec.windows)
        self.snapshot = SessionSnapshot(spec.session_name, True, windows, "pm")

    def terminate_session(self, name):
        self.terminated.append(name)
        self.snapshot = SessionSnapshot.stopped(name)

    def attach_session(self, _name):
        return None


class FakeStateStore:
    def __init__(self) -> None:
        self.states = []
        self.lock_count = 0

    def locked(self, _project):
        store = self

        class Lock:
            def __enter__(self):
                store.lock_count += 1

            def __exit__(self, _error_type, _error, _traceback):
                return False

        return Lock()

    def write(self, _project, state):
        self.states.append(state)

    def read(self, _project):
        return self.states[-1] if self.states else None


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
    service = SessionService(
        project=project,
        configuration=FakeConfig(),
        prompts=FakePromptRenderer(tmp_path / "runtime"),
        adapters=FakeRegistry(FakeAdapter(adapter_available)),
        backend=backend,
        state_store=state_store,
        atcode_home=tmp_path / "runtime",
    )
    return service, backend, state_store


def test_start_preflights_all_adapters_before_backend_create(tmp_path: Path) -> None:
    service, backend, _state_store = make_service(tmp_path, adapter_available=False)

    with pytest.raises(AtCodeError, match="ADAPTER_NOT_FOUND"):
        service.start()

    assert backend.created_specs == []


def test_start_creates_five_role_windows_and_persists_running_state(tmp_path: Path) -> None:
    service, backend, state_store = make_service(tmp_path)

    state = service.start()

    assert state.status is Lifecycle.RUNNING
    assert len(backend.created_specs[0].windows) == 5
    assert state_store.states[-1] == state


def test_start_is_idempotent_when_session_already_exists(tmp_path: Path) -> None:
    service, backend, _state_store = make_service(tmp_path)
    service.start()

    state = service.start()

    assert state.status is Lifecycle.RUNNING
    assert len(backend.created_specs) == 1


def test_start_rejects_an_existing_degraded_session(tmp_path: Path) -> None:
    service, backend, state_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        ("pm", "developer"),
        "pm",
    )

    with pytest.raises(AtCodeError, match="SESSION_DEGRADED"):
        service.start()

    assert state_store.states[-1].status is Lifecycle.DEGRADED
    assert backend.created_specs == []


def test_stop_is_idempotent(tmp_path: Path) -> None:
    service, backend, _state_store = make_service(tmp_path)

    state = service.stop()

    assert state.status is Lifecycle.STOPPED
    assert backend.terminated == []


def test_repeated_stop_preserves_the_original_stop_timestamp(tmp_path: Path) -> None:
    service, _backend, _state_store = make_service(tmp_path)
    service.start()

    first = service.stop()
    second = service.stop()

    assert first.stopped_at is not None
    assert second.stopped_at == first.stopped_at


def test_status_is_degraded_when_role_window_is_missing(tmp_path: Path) -> None:
    service, backend, _state_store = make_service(tmp_path)
    backend.snapshot = SessionSnapshot(
        "atcode-target-1234567890",
        True,
        ("pm", "developer"),
        "pm",
    )

    state = service.status()

    assert state.status is Lifecycle.DEGRADED


def test_status_updates_state_while_holding_project_lock(tmp_path: Path) -> None:
    service, _backend, state_store = make_service(tmp_path)

    service.status()

    assert state_store.lock_count == 1


def test_status_preserves_stopped_timestamp(tmp_path: Path) -> None:
    service, _backend, _state_store = make_service(tmp_path)
    stopped = service.stop()

    current = service.status()

    assert stopped.stopped_at is not None
    assert current.stopped_at == stopped.stopped_at
