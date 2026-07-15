from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import LaunchSpec, SessionSpec, WindowSpec
from atcode.infrastructure.process import CommandResult
from atcode.infrastructure.tmux_backend import TmuxBackend


class FakeRunner:
    def __init__(self, results: Sequence[tuple[int, str, str]]) -> None:
        self._results = list(results)
        self.calls: list[tuple[str, ...]] = []
        self.interactive_calls: list[tuple[str, ...]] = []

    def run(self, argv, **_kwargs) -> CommandResult:
        command = tuple(argv)
        self.calls.append(command)
        returncode, stdout, stderr = self._results.pop(0)
        return CommandResult(command, returncode, stdout, stderr)

    def run_interactive(self, argv, **_kwargs) -> int:
        self.interactive_calls.append(tuple(argv))
        return 0


def session_spec(tmp_path: Path) -> SessionSpec:
    roles = ("pm", "developer", "reviewer", "tester", "docs")
    windows = tuple(
        WindowSpec(
            name=role,
            cwd=tmp_path,
            launch=LaunchSpec(
                executable="agent-cli",
                arguments=(f"{role} prompt",),
                environment={"ATCODE_ROLE": role},
            ),
        )
        for role in roles
    )
    return SessionSpec("atcode-target-1234567890", tmp_path, windows)


def test_create_session_builds_all_role_windows(tmp_path: Path) -> None:
    runner = FakeRunner([(1, "", "")] + [(0, "", "")] * 6)
    backend = TmuxBackend(runner, {})

    backend.create_session(session_spec(tmp_path))

    assert runner.calls[0][:3] == ("tmux", "has-session", "-t")
    assert sum("new-session" in command for command in runner.calls) == 1
    assert sum("new-window" in command for command in runner.calls) == 4
    assert any("select-window" in command for command in runner.calls)
    assert all("send-keys" not in command for command in runner.calls)
    assert all("capture-pane" not in command for command in runner.calls)


def test_partial_creation_rolls_back_new_session(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (1, "", ""),
            (0, "", ""),
            (0, "", ""),
            (1, "", "window failed"),
            (0, "", ""),
        ]
    )
    backend = TmuxBackend(runner, {})

    with pytest.raises(AtCodeError, match="TMUX_CREATE_FAILED"):
        backend.create_session(session_spec(tmp_path))

    assert "kill-session" in runner.calls[-1]


def test_existing_session_is_not_killed(tmp_path: Path) -> None:
    runner = FakeRunner([(0, "", "")])
    backend = TmuxBackend(runner, {})

    with pytest.raises(AtCodeError, match="TMUX_SESSION_EXISTS"):
        backend.create_session(session_spec(tmp_path))

    assert all("kill-session" not in command for command in runner.calls)


def test_inspect_session_returns_actual_windows(tmp_path: Path) -> None:
    runner = FakeRunner(
        [
            (0, "", ""),
            (0, "pm\t1\ndeveloper\t0\nreviewer\t0\n", ""),
        ]
    )
    backend = TmuxBackend(runner, {})

    snapshot = backend.inspect_session("atcode-target-1234567890")

    assert snapshot.exists is True
    assert snapshot.windows == ("pm", "developer", "reviewer")
    assert snapshot.active_window == "pm"


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
