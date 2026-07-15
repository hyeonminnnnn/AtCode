"""Safe subprocess boundary used by Runtime integrations."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from atcode.domain.errors import AtCodeError


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class SubprocessRunner:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float = 15,
    ) -> CommandResult:
        command = tuple(argv)
        if not command:
            raise ValueError("argv must not be empty")
        process_env = None if env is None else {**os.environ, **env}
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=process_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                shell=False,
            )
        except FileNotFoundError as error:
            raise AtCodeError(
                "PROCESS_NOT_FOUND",
                f"Executable not found: {command[0]}",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise AtCodeError(
                "PROCESS_TIMEOUT",
                f"Command timed out: {command[0]}",
            ) from error
        return CommandResult(
            argv=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def run_interactive(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        command = tuple(argv)
        if not command:
            raise ValueError("argv must not be empty")
        process_env = None if env is None else {**os.environ, **env}
        try:
            return subprocess.run(
                command,
                cwd=cwd,
                env=process_env,
                check=False,
                shell=False,
            ).returncode
        except FileNotFoundError as error:
            raise AtCodeError(
                "PROCESS_NOT_FOUND",
                f"Executable not found: {command[0]}",
            ) from error
