from __future__ import annotations

from io import StringIO
from pathlib import Path

from atcode.application.diagnostics import DiagnosticsService
from atcode.bootstrap import build_container
from atcode.cli import run
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Layout,
    LaunchSpec,
    Role,
    RoleEndpoint,
    SessionSnapshot,
    WorkflowState,
    WorkflowStatus,
)
from atcode.infrastructure.adapters.registry import AdapterRegistry


class FakeAdapter:
    def __init__(self, name: str, available: bool = True) -> None:
        self.name = name
        self.available = available

    def probe(self):
        level = DiagnosticLevel.PASS if self.available else DiagnosticLevel.FAIL
        hint = None if self.available else "WSL용 Codex를 설치하세요."
        return DiagnosticResult(self.name, level, f"{self.name} probe", hint)

    def build_launch(self, context):
        return LaunchSpec(self.name, (context.prompt.text,), {})


class FakeBackend:
    def __init__(self) -> None:
        self.snapshots = {}
        self.outputs = {}
        self.deliveries = []
        self.messages = []
        self.next_action_result = DiagnosticResult(
            "next-action",
            DiagnosticLevel.PASS,
            "Ctrl+b Enter",
        )

    def probe(self):
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, "tmux fake")

    def inspect_session(self, name):
        return self.snapshots.get(name, SessionSnapshot.stopped(name))

    def create_session(self, spec):
        window = "team" if spec.layout is Layout.PANES else None
        self.snapshots[spec.session_name] = SessionSnapshot(
            spec.session_name,
            True,
            spec.layout,
            tuple(
                RoleEndpoint(
                    item.role,
                    window or item.role.value,
                    f"%{index}",
                    index == 1,
                )
                for index, item in enumerate(spec.roles, start=1)
            ),
        )

    def terminate_session(self, name):
        self.snapshots[name] = SessionSnapshot.stopped(name)

    def attach_session(self, _name):
        return None

    def read_role_output(self, _session_name, role):
        return self.outputs[role]

    def deliver_text(self, _session_name, role, text):
        self.deliveries.append((role, text))

    def focus_role(self, session_name, role):
        snapshot = self.snapshots[session_name]
        self.snapshots[session_name] = SessionSnapshot(
            session_name,
            True,
            snapshot.layout,
            tuple(
                RoleEndpoint(item.role, item.window, item.pane, item.role is role)
                for item in snapshot.endpoints
            ),
        )

    def install_next_action(self):
        return self.next_action_result

    def next_action_probe(self):
        return self.next_action_result

    def display_message(self, message):
        self.messages.append(message)


def invoke(container, cwd: Path, *argv: str, stdin_text: str = ""):
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run(
        list(argv),
        container=container,
        cwd=cwd,
        stdin=StringIO(stdin_text),
        stdout=stdout,
        stderr=stderr,
    )
    return exit_code, stdout.getvalue(), stderr.getvalue()


def make_container(tmp_path: Path, *, codex_available: bool = True):
    adapters = AdapterRegistry(
        (
            FakeAdapter("codex", codex_available),
            FakeAdapter("claude"),
            FakeAdapter("gemini"),
            FakeAdapter("shell"),
        )
    )
    return build_container(
        env={"ATCODE_HOME": str(tmp_path / "runtime")},
        install_root=Path(__file__).resolve().parents[2],
        backend=FakeBackend(),
        adapters=adapters,
    )


def test_init_creates_runtime_project_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    before = set(target.rglob("*"))
    container = make_container(tmp_path)

    exit_code, stdout, stderr = invoke(
        container,
        target,
        "init",
        "--project",
        str(target),
    )

    assert exit_code == 0
    assert "초기화" in stdout
    assert stderr == ""
    assert set(target.rglob("*")) == before
    assert list((tmp_path / "runtime" / "projects").iterdir())


def test_lifecycle_commands_use_registered_project(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")

    start_code, start_out, _ = invoke(container, target, "start")
    status_code, status_out, _ = invoke(container, target, "status")
    stop_code, stop_out, _ = invoke(container, target, "stop")

    assert (start_code, status_code, stop_code) == (0, 0, 0)
    assert "running" in start_out
    assert "running" in status_out
    assert "stopped" in stop_out


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


def test_internal_next_rejects_unknown_session_without_traceback(
    tmp_path: Path,
) -> None:
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


def test_start_fresh_requires_stopped_session_and_confirmation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")

    running_code, _out, running_error = invoke(
        container,
        target,
        "start",
        "--fresh",
        stdin_text="y\n",
    )
    assert running_code == 1
    assert "FRESH_REQUIRES_STOPPED_SESSION" in running_error

    invoke(container, target, "stop")
    cancelled_code, _out, cancelled_error = invoke(
        container,
        target,
        "start",
        "--fresh",
        stdin_text="n\n",
    )
    assert cancelled_code == 1
    assert "FRESH_CANCELLED" in cancelled_error


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
        container,
        target,
        "start",
        "--fresh",
        stdin_text="y\n",
    )

    assert code == 0
    assert "초기화" in stdout
    assert stderr == ""
    assert container.workflows(project).current().status is WorkflowStatus.IDLE


def test_project_config_override_is_visible(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")

    code, _stdout, _stderr = invoke(
        container,
        target,
        "config",
        "set",
        "roles.reviewer.adapter",
        "codex",
    )
    show_code, show_out, _ = invoke(container, target, "config", "show")

    assert code == show_code == 0
    assert '"pm"' in show_out
    assert '"developer"' in show_out
    assert '"reviewer"' in show_out
    assert '"codex"' in show_out
    assert '"tester"' not in show_out
    assert '"docs"' not in show_out


def test_unregistered_project_error_has_no_traceback(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)

    code, _stdout, stderr = invoke(container, target, "status")

    assert code == 1
    assert "PROJECT_NOT_INITIALIZED" in stderr
    assert "Traceback" not in stderr


def test_doctor_reports_missing_adapter_without_traceback(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path, codex_available=False)
    invoke(container, target, "init")

    code, stdout, stderr = invoke(container, target, "doctor")

    assert code == 1
    assert "FAIL" in stdout
    assert "codex" in stdout
    assert "WSL용 Codex를 설치하세요." in stdout
    assert "Traceback" not in stderr


def test_doctor_reports_workflow_endpoints_and_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DiagnosticsService,
        "_platform",
        staticmethod(
            lambda: DiagnosticResult(
                "platform",
                DiagnosticLevel.PASS,
                "linux",
            )
        ),
    )
    target = tmp_path / "target"
    target.mkdir()
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")

    code, stdout, stderr = invoke(container, target, "doctor")

    assert code == 0
    assert "workflow" in stdout
    assert "pm, developer, reviewer" in stdout
    assert "next-action" in stdout
    assert "Traceback" not in stderr


def test_doctor_binding_warning_keeps_success_exit_code(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        DiagnosticsService,
        "_platform",
        staticmethod(
            lambda: DiagnosticResult(
                "platform",
                DiagnosticLevel.PASS,
                "linux",
            )
        ),
    )
    container = make_container(tmp_path)
    container.backend.next_action_result = DiagnosticResult(
        "next-action",
        DiagnosticLevel.WARN,
        "Ctrl+b Enter conflict",
        "Use atcode next.",
    )

    code, stdout, stderr = invoke(container, tmp_path, "doctor")

    assert code == 0
    assert "WARN" in stdout
    assert "Use atcode next." in stdout
    assert stderr == ""
