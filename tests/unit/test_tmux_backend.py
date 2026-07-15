from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Layout, LaunchSpec, Role, RoleSpec, SessionSpec
from atcode.infrastructure.process import CommandResult
from atcode.infrastructure.tmux_backend import TmuxBackend


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


def test_create_panes_session_uses_one_window_and_three_role_panes(
    tmp_path: Path,
) -> None:
    runner = LayoutRunner(Layout.PANES)
    backend = TmuxBackend(runner, {})

    backend.create_session(session_spec(tmp_path, Layout.PANES))

    assert runner.calls[0].argv[:3] == ("tmux", "has-session", "-t")
    assert sum("new-session" in call.argv for call in runner.calls) == 1
    assert sum("split-window" in call.argv for call in runner.calls) == 2
    assert all("new-window" not in call.argv for call in runner.calls)
    assert any("select-layout" in call.argv for call in runner.calls)
    assert any("pane-border-format" in call.argv for call in runner.calls)
    assert all("send-keys" not in call.argv for call in runner.calls)
    assert all("capture-pane" not in call.argv for call in runner.calls)


def test_create_windows_session_keeps_three_windows(tmp_path: Path) -> None:
    runner = LayoutRunner(Layout.WINDOWS)
    backend = TmuxBackend(runner, {})

    backend.create_session(session_spec(tmp_path, Layout.WINDOWS))

    assert sum("new-session" in call.argv for call in runner.calls) == 1
    assert sum("new-window" in call.argv for call in runner.calls) == 2
    assert all("split-window" not in call.argv for call in runner.calls)


def test_create_session_rolls_back_when_window_verification_fails(
    tmp_path: Path,
) -> None:
    runner = LayoutRunner(Layout.PANES, missing_role=Role.REVIEWER)
    backend = TmuxBackend(runner, {})

    with pytest.raises(AtCodeError, match="TMUX_CREATE_FAILED"):
        backend.create_session(session_spec(tmp_path))

    assert "kill-session" in runner.calls[-1].argv


def test_partial_creation_rolls_back_new_session(tmp_path: Path) -> None:
    runner = LayoutRunner(Layout.PANES, fail_operation="split-window")
    backend = TmuxBackend(runner, {})

    with pytest.raises(AtCodeError, match="TMUX_CREATE_FAILED"):
        backend.create_session(session_spec(tmp_path))

    assert "kill-session" in runner.calls[-1].argv


def test_existing_session_is_not_killed(tmp_path: Path) -> None:
    runner = LayoutRunner(Layout.PANES, initial_exists=True)
    backend = TmuxBackend(runner, {})

    with pytest.raises(AtCodeError, match="TMUX_SESSION_EXISTS"):
        backend.create_session(session_spec(tmp_path))

    assert all("kill-session" not in call.argv for call in runner.calls)


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

    assert snapshot.exists is True
    assert snapshot.layout is Layout.PANES
    assert tuple(endpoint.role for endpoint in snapshot.endpoints) == tuple(Role)
    assert snapshot.active_role is Role.PM


def test_attach_switches_client_when_already_in_tmux() -> None:
    runner = FakeRunner([])
    backend = TmuxBackend(runner, {"TMUX": "/tmp/tmux-1000/default,1,0"})

    backend.attach_session("atcode-target-1234567890")

    assert runner.interactive_calls == [
        ("tmux", "switch-client", "-t", "=atcode-target-1234567890")
    ]


def test_session_name_rejects_shell_metacharacters() -> None:
    backend = TmuxBackend(FakeRunner([]), {})

    with pytest.raises(AtCodeError, match="SESSION_NAME_INVALID"):
        backend.session_exists("bad; rm -rf")
