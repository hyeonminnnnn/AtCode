from __future__ import annotations

import subprocess
import sys
from unittest.mock import patch

import pytest

from atcode.domain.errors import AtCodeError
from atcode.infrastructure.process import SubprocessRunner


def test_shell_metacharacters_are_passed_as_literal_arguments() -> None:
    runner = SubprocessRunner()
    value = "hello; echo unsafe"

    result = runner.run(
        (sys.executable, "-c", "import sys; print(sys.argv[1])", value)
    )

    assert result.returncode == 0
    assert result.stdout.strip() == value
    assert result.argv[-1] == value


def test_missing_executable_becomes_structured_error() -> None:
    runner = SubprocessRunner()

    with pytest.raises(AtCodeError, match="PROCESS_NOT_FOUND"):
        runner.run(("atcode-command-that-does-not-exist", "--version"))


def test_os_error_becomes_structured_error(monkeypatch) -> None:
    def deny(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(subprocess, "run", deny)

    with pytest.raises(AtCodeError, match="PROCESS_FAILED"):
        SubprocessRunner().run(("tmux", "-V"))


@patch("atcode.infrastructure.process.subprocess.run")
def test_runner_passes_text_to_stdin_without_shell(mock_run) -> None:
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = ""
    mock_run.return_value.stderr = ""

    SubprocessRunner().run(("tmux", "load-buffer", "-"), input_text="$(touch bad)")

    assert mock_run.call_args.kwargs["input"] == "$(touch bad)"
    assert mock_run.call_args.kwargs["shell"] is False
