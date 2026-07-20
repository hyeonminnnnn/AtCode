from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from atcode.application.diagnostics import DiagnosticsService
from atcode.bootstrap import RuntimePaths
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Layout,
    Lifecycle,
    Project,
    Role,
    RoleAssignment,
    RoleEndpoint,
    RoleRuntime,
    RuntimeConfig,
    RuntimeState,
    SessionSnapshot,
    WorkflowState,
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
    def __init__(
        self,
        snapshot: SessionSnapshot,
        next_action: DiagnosticResult | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.next_action = next_action or DiagnosticResult(
            "next-action",
            DiagnosticLevel.PASS,
            "Ctrl+b Enter",
        )

    def probe(self):
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, "available")

    def inspect_session(self, _name):
        return self.snapshot

    def next_action_probe(self):
        return self.next_action


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


class FakeWorkflowStore:
    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid

    def read_workflow(self, _project):
        if self.invalid:
            raise AtCodeError(
                "WORKFLOW_INVALID",
                "broken workflow",
                hint="repair it",
            )
        return WorkflowState.initial()

    def read_handoff(self, _project):
        return None


class FakeProjectLock:
    @contextmanager
    def locked(self, _project):
        yield


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
    next_action=None,
    workflow_invalid: bool = False,
) -> DiagnosticsService:
    home = tmp_path / "runtime"
    return DiagnosticsService(
        paths=RuntimePaths(home, home / "projects", home / "config.json"),
        configuration=configuration or FakeConfiguration(),
        adapters=FakeAdapters(),
        backend=FakeBackend(
            snapshot or SessionSnapshot.stopped("session"),
            next_action,
        ),
        prompts=prompts or FakePrompts(),
        state_store=FakeStateStore(state),
        workflow_store=FakeWorkflowStore(invalid=workflow_invalid),
        project_lock=FakeProjectLock(),
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


def test_doctor_accepts_matching_role_endpoints_and_layout(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    state = RuntimeState(
        project.project_id,
        "tmux",
        f"atcode-{project.project_id}",
        Lifecycle.RUNNING,
        "started",
        None,
        tuple(
            RoleRuntime(role, "codex", f"%{index}")
            for index, role in enumerate(Role, 1)
        ),
        layout=Layout.PANES,
    )
    snapshot = SessionSnapshot(
        f"atcode-{project.project_id}",
        True,
        Layout.PANES,
        tuple(
            RoleEndpoint(role, "team", f"%{index}", index == 1)
            for index, role in enumerate(Role, 1)
        ),
    )
    service = make_service(tmp_path, state=state, snapshot=snapshot)

    results = service.run(project)

    consistency = next(item for item in results if item.name == "state/session")
    assert consistency.level is DiagnosticLevel.PASS


def test_doctor_reports_role_endpoints_and_next_binding(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    snapshot = SessionSnapshot(
        f"atcode-{project.project_id}",
        True,
        Layout.PANES,
        tuple(
            RoleEndpoint(role, "team", f"%{index}", index == 1)
            for index, role in enumerate(Role, 1)
        ),
    )
    state = RuntimeState(
        project.project_id,
        "tmux",
        f"atcode-{project.project_id}",
        Lifecycle.RUNNING,
        "started",
        None,
        tuple(RoleRuntime(role, "codex", role.value) for role in Role),
        layout=Layout.PANES,
    )
    service = make_service(tmp_path, snapshot=snapshot, state=state)

    results = service.run(project)

    by_name = {result.name: result for result in results}
    assert by_name["state/session"].level is DiagnosticLevel.PASS
    assert "pm, developer, reviewer" in by_name["state/session"].message
    assert by_name["next-action"].level is DiagnosticLevel.PASS


def test_doctor_warns_when_enter_binding_conflicts(tmp_path: Path) -> None:
    service = make_service(
        tmp_path,
        next_action=DiagnosticResult(
            "next-action",
            DiagnosticLevel.WARN,
            "Ctrl+b Enter is already bound.",
            hint="Use atcode next.",
        ),
    )

    results = service.run(None)

    binding = next(result for result in results if result.name == "next-action")
    assert binding.level is DiagnosticLevel.WARN
    assert binding.hint == "Use atcode next."


def test_doctor_fails_for_invalid_workflow(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service = make_service(tmp_path, workflow_invalid=True)

    results = service.run(project)

    workflow = next(result for result in results if result.name == "workflow")
    assert workflow.level is DiagnosticLevel.FAIL
    assert workflow.hint is not None
    assert "repair" in workflow.hint.lower()
