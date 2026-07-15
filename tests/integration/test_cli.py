from __future__ import annotations

from io import StringIO
from pathlib import Path

from atcode.bootstrap import build_container
from atcode.cli import run
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Layout,
    LaunchSpec,
    RoleEndpoint,
    SessionSnapshot,
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


def invoke(container, cwd: Path, *argv: str):
    stdout = StringIO()
    stderr = StringIO()
    exit_code = run(list(argv), container=container, cwd=cwd, stdout=stdout, stderr=stderr)
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
