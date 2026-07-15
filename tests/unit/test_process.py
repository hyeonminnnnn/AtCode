from __future__ import annotations

import sys

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
