"""tmux implementation of the Phase 1 Terminal Backend contract."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    LaunchSpec,
    SessionSnapshot,
    SessionSpec,
    WindowSpec,
)
from atcode.infrastructure.process import CommandResult, SubprocessRunner

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class TmuxBackend:
    def __init__(
        self,
        runner: SubprocessRunner,
        env: Mapping[str, str],
    ) -> None:
        self._runner = runner
        self._env = env

    def probe(self) -> DiagnosticResult:
        try:
            result = self._runner.run(("tmux", "-V"))
        except AtCodeError as error:
            return DiagnosticResult(
                "tmux",
                DiagnosticLevel.FAIL,
                error.message,
                hint="Install tmux in WSL2 or Linux.",
            )
        if result.returncode != 0:
            return DiagnosticResult(
                "tmux",
                DiagnosticLevel.FAIL,
                result.stderr.strip() or "tmux is unavailable.",
            )
        return DiagnosticResult("tmux", DiagnosticLevel.PASS, result.stdout.strip())

    def session_exists(self, session_name: str) -> bool:
        self._validate_identifier(session_name, "session")
        result = self._runner.run(
            ("tmux", "has-session", "-t", f"={session_name}")
        )
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise self._command_error("has-session", result)

    def create_session(self, spec: SessionSpec) -> None:
        self._validate_identifier(spec.session_name, "session")
        if not spec.windows:
            raise AtCodeError("SESSION_SPEC_INVALID", "At least one window is required.")
        if self.session_exists(spec.session_name):
            raise AtCodeError(
                "TMUX_SESSION_EXISTS",
                f"tmux session already exists: {spec.session_name}",
            )

        created = False
        try:
            first, *remaining = spec.windows
            self._create_first_window(spec.session_name, first)
            created = True
            for window in remaining:
                self._create_window(spec.session_name, window)
            self._run_checked(
                (
                    "tmux",
                    "select-window",
                    "-t",
                    f"={spec.session_name}:{first.name}",
                ),
                "select-window",
            )
        except AtCodeError as error:
            if created:
                self._runner.run(
                    ("tmux", "kill-session", "-t", f"={spec.session_name}")
                )
            raise AtCodeError(
                "TMUX_CREATE_FAILED",
                f"Could not create tmux session: {spec.session_name}",
                hint=error.message,
            ) from error

    def inspect_session(self, session_name: str) -> SessionSnapshot:
        self._validate_identifier(session_name, "session")
        if not self.session_exists(session_name):
            return SessionSnapshot.stopped(session_name)
        result = self._run_checked(
            (
                "tmux",
                "list-windows",
                "-t",
                f"={session_name}",
                "-F",
                "#{window_name}\t#{window_active}",
            ),
            "list-windows",
        )
        windows: list[str] = []
        active: str | None = None
        for line in result.stdout.splitlines():
            name, separator, is_active = line.partition("\t")
            if not separator:
                raise AtCodeError("TMUX_OUTPUT_INVALID", "Invalid tmux window output.")
            windows.append(name)
            if is_active == "1":
                active = name
        return SessionSnapshot(session_name, True, tuple(windows), active)

    def attach_session(self, session_name: str) -> None:
        self._validate_identifier(session_name, "session")
        command = "switch-client" if self._env.get("TMUX") else "attach-session"
        returncode = self._runner.run_interactive(
            ("tmux", command, "-t", f"={session_name}")
        )
        if returncode != 0:
            raise AtCodeError("TMUX_ATTACH_FAILED", "Could not attach tmux session.")

    def terminate_session(self, session_name: str) -> None:
        self._validate_identifier(session_name, "session")
        if self.session_exists(session_name):
            self._run_checked(
                ("tmux", "kill-session", "-t", f"={session_name}"),
                "kill-session",
            )

    def _create_first_window(self, session_name: str, window: WindowSpec) -> None:
        self._validate_identifier(window.name, "window")
        self._run_checked(
            (
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                window.name,
                "-c",
                str(window.cwd),
                self._launch_command(window.launch),
            ),
            "new-session",
        )

    def _create_window(self, session_name: str, window: WindowSpec) -> None:
        self._validate_identifier(window.name, "window")
        self._run_checked(
            (
                "tmux",
                "new-window",
                "-d",
                "-t",
                f"={session_name}",
                "-n",
                window.name,
                "-c",
                str(window.cwd),
                self._launch_command(window.launch),
            ),
            "new-window",
        )

    @staticmethod
    def _launch_command(spec: LaunchSpec) -> str:
        environment = spec.environment or {}
        command = (
            "env",
            *(f"{key}={value}" for key, value in sorted(environment.items())),
            spec.executable,
            *spec.arguments,
        )
        return shlex.join(command)

    def _run_checked(self, argv: tuple[str, ...], operation: str) -> CommandResult:
        result = self._runner.run(argv)
        if result.returncode != 0:
            raise self._command_error(operation, result)
        return result

    @staticmethod
    def _command_error(operation: str, result: CommandResult) -> AtCodeError:
        detail = result.stderr.strip() or "tmux command failed."
        return AtCodeError("TMUX_COMMAND_FAILED", f"{operation}: {detail}")

    @staticmethod
    def _validate_identifier(value: str, kind: str) -> None:
        if not _IDENTIFIER.fullmatch(value):
            raise AtCodeError(
                "SESSION_NAME_INVALID",
                f"Invalid {kind} name: {value}",
                exit_code=2,
            )
