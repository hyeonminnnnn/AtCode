from __future__ import annotations

from pathlib import Path

from atcode.application.diagnostics import DiagnosticsService
from atcode.bootstrap import RuntimePaths
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Lifecycle,
    Project,
    Role,
    RoleAssignment,
    RoleRuntime,
    RuntimeConfig,
    RuntimeState,
    SessionSnapshot,
)


class FakeConfiguration:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid

    def effective(self, _project):
        if not self.valid:
            raise AtCodeError("CONFIG_INVALID", "broken config", hint="repair it")
        return RuntimeConfig(
            "tmux",
            {role: RoleAssignment("codex") for role in Role},
        )


class FakeAdapter:
    def probe(self):
        return DiagnosticResult("codex", DiagnosticLevel.PASS, "available")


class FakeAdapters:
    def get(self, _name):
        return FakeAdapter()


class FakeBackend:
    def __init__(self, snapshot: SessionSnapshot) -> None:
        self.snapshot = snapshot

    def probe(self):
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, "available")

    def inspect_session(self, _name):
        return self.snapshot


class FakePrompts:
    def __init__(self, *, valid: bool = True) -> None:
        self.valid = valid

    def validate_templates(self):
        if not self.valid:
            raise AtCodeError("PROMPT_TEMPLATE_MISSING", "missing prompt")


class FakeStateStore:
    def __init__(self, state: RuntimeState | None = None) -> None:
        self.state = state

    def read(self, _project):
        return self.state


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    return Project("target-1234567890", "target", root, "created")


def make_service(
    tmp_path: Path,
    *,
    configuration=None,
    prompts=None,
    snapshot=None,
    state=None,
) -> DiagnosticsService:
    home = tmp_path / "runtime"
    return DiagnosticsService(
        paths=RuntimePaths(home, home / "projects", home / "config.json"),
        configuration=configuration or FakeConfiguration(),
        adapters=FakeAdapters(),
        backend=FakeBackend(snapshot or SessionSnapshot.stopped("session")),
        prompts=prompts or FakePrompts(),
        state_store=FakeStateStore(state),
    )


def test_doctor_reports_config_and_prompt_errors_without_raising(
    tmp_path: Path,
) -> None:
    service = make_service(
        tmp_path,
        configuration=FakeConfiguration(valid=False),
        prompts=FakePrompts(valid=False),
    )

    results = service.run(None)

    failures = {item.name for item in results if item.level is DiagnosticLevel.FAIL}
    assert {"config", "prompts"}.issubset(failures)


def test_doctor_warns_when_persisted_state_disagrees_with_tmux(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    state = RuntimeState(
        project.project_id,
        "tmux",
        f"atcode-{project.project_id}",
        Lifecycle.RUNNING,
        "started",
        None,
        tuple(RoleRuntime(role, "codex", role.value) for role in Role),
    )
    service = make_service(tmp_path, state=state)

    results = service.run(project)

    consistency = next(item for item in results if item.name == "state/session")
    assert consistency.level is DiagnosticLevel.WARN
