"""tmux implementation of the Terminal Backend contract."""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Layout,
    LaunchSpec,
    Role,
    RoleEndpoint,
    RoleSpec,
    SessionSnapshot,
    SessionSpec,
)
from atcode.infrastructure.process import CommandResult, SubprocessRunner

_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_NEXT_ACTION = (
    'atcode next --session "#{session_name}" '
    '--pane "#{pane_id}" --notify'
)


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
        if (
            {item.role for item in spec.roles} != set(Role)
            or len(spec.roles) != len(Role)
        ):
            raise AtCodeError(
                "SESSION_SPEC_INVALID",
                "Exactly one endpoint for every role is required.",
            )
        if self.session_exists(spec.session_name):
            raise AtCodeError(
                "TMUX_SESSION_EXISTS",
                f"tmux session already exists: {spec.session_name}",
            )

        created = False
        try:
            created = True
            if spec.layout is Layout.PANES:
                self._create_panes_session(spec)
            else:
                self._create_windows_session(spec)
            snapshot = self.inspect_session(spec.session_name)
            actual_roles = {endpoint.role for endpoint in snapshot.endpoints}
            if (
                actual_roles != set(Role)
                or len(snapshot.endpoints) != len(Role)
                or snapshot.layout is not spec.layout
            ):
                raise AtCodeError(
                    "TMUX_ENDPOINT_SET_INVALID",
                    "tmux did not create every requested role endpoint.",
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
                "list-panes",
                "-s",
                "-t",
                f"={session_name}",
                "-F",
                "#{@atcode_role}\t#{window_name}\t#{pane_id}\t#{pane_active}",
            ),
            "list-panes",
        )
        endpoints: list[RoleEndpoint] = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) != 4:
                raise AtCodeError("TMUX_OUTPUT_INVALID", "Invalid tmux pane output.")
            role_name, window, pane, is_active = fields
            try:
                role = Role(role_name)
            except ValueError:
                continue
            endpoints.append(RoleEndpoint(role, window, pane, is_active == "1"))
        layout = self._detect_layout(endpoints)
        return SessionSnapshot(session_name, True, layout, tuple(endpoints))

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

    def read_role_output(self, session_name: str, role: Role) -> str:
        endpoint = self._resolve_role_endpoint(session_name, role)
        return self._run_checked(
            (
                "tmux",
                "capture-pane",
                "-p",
                "-S",
                "-",
                "-t",
                endpoint.pane,
            ),
            "capture-pane",
        ).stdout

    def deliver_text(self, session_name: str, role: Role, text: str) -> None:
        endpoint = self._resolve_role_endpoint(session_name, role)
        result = self._runner.run(
            ("tmux", "load-buffer", "-b", "atcode-transfer", "-"),
            input_text=text,
        )
        if result.returncode != 0:
            raise self._command_error("load-buffer", result)
        self._run_checked(
            (
                "tmux",
                "paste-buffer",
                "-p",
                "-d",
                "-b",
                "atcode-transfer",
                "-t",
                endpoint.pane,
            ),
            "paste-buffer",
        )
        self._run_checked(
            ("tmux", "send-keys", "-t", endpoint.pane, "Enter"),
            "send-keys",
        )

    def focus_role(self, session_name: str, role: Role) -> None:
        endpoint = self._resolve_role_endpoint(session_name, role)
        if endpoint.window != "team":
            self._validate_identifier(endpoint.window, "window")
            self._run_checked(
                (
                    "tmux",
                    "select-window",
                    "-t",
                    f"={session_name}:{endpoint.window}",
                ),
                "select-window",
            )
        self._run_checked(
            ("tmux", "select-pane", "-t", endpoint.pane),
            "select-pane",
        )

    def install_next_action(self) -> DiagnosticResult:
        existing = self._runner.run(
            ("tmux", "list-keys", "-T", "prefix", "Enter")
        )
        if existing.returncode == 0:
            if "atcode next" in existing.stdout:
                return DiagnosticResult(
                    "next-action",
                    DiagnosticLevel.PASS,
                    "Ctrl+b Enter is already bound to atcode next.",
                )
            return DiagnosticResult(
                "next-action",
                DiagnosticLevel.WARN,
                "Ctrl+b Enter already has another tmux binding.",
                hint="Use the atcode next command instead.",
            )
        result = self._runner.run(
            (
                "tmux",
                "bind-key",
                "-T",
                "prefix",
                "Enter",
                "run-shell",
                _NEXT_ACTION,
            )
        )
        if result.returncode != 0:
            return DiagnosticResult(
                "next-action",
                DiagnosticLevel.WARN,
                result.stderr.strip() or "Could not install Ctrl+b Enter binding.",
                hint="Use the atcode next command instead.",
            )
        return DiagnosticResult(
            "next-action",
            DiagnosticLevel.PASS,
            "Ctrl+b Enter is bound to atcode next.",
        )

    def next_action_probe(self) -> DiagnosticResult:
        result = self._runner.run(
            ("tmux", "list-keys", "-T", "prefix", "Enter")
        )
        if result.returncode == 0 and "atcode next" in result.stdout:
            return DiagnosticResult(
                "next-action",
                DiagnosticLevel.PASS,
                "Ctrl+b Enter is bound to atcode next.",
            )
        return DiagnosticResult(
            "next-action",
            DiagnosticLevel.WARN,
            "Ctrl+b Enter is not bound to atcode next.",
            hint="Run atcode start or use the atcode next command.",
        )

    def display_message(self, message: str) -> None:
        self._run_checked(
            ("tmux", "display-message", "-d", "1000", "--", message),
            "display-message",
        )

    def _resolve_role_endpoint(
        self,
        session_name: str,
        role: Role,
    ) -> RoleEndpoint:
        snapshot = self.inspect_session(session_name)
        matches = [item for item in snapshot.endpoints if item.role is role]
        if len(matches) != 1:
            raise AtCodeError(
                "TMUX_ROLE_ENDPOINT_INVALID",
                f"Expected one tmux endpoint for role: {role.value}",
            )
        return matches[0]

    def _create_panes_session(self, spec: SessionSpec) -> None:
        by_role = {item.role: item for item in spec.roles}
        first = by_role[Role.PM]
        self._create_first_role(spec.session_name, "team", first)
        self._set_role_metadata(
            f"={spec.session_name}:team.0",
            Role.PM,
        )
        for role in (Role.DEVELOPER, Role.REVIEWER):
            item = by_role[role]
            result = self._run_checked(
                (
                    "tmux",
                    "split-window",
                    "-d",
                    "-P",
                    "-F",
                    "#{pane_id}",
                    "-t",
                    f"={spec.session_name}:team",
                    "-c",
                    str(item.cwd),
                    self._launch_command(item.launch),
                ),
                "split-window",
            )
            pane_id = result.stdout.strip()
            if not pane_id:
                raise AtCodeError("TMUX_OUTPUT_INVALID", "tmux pane id is missing.")
            self._set_role_metadata(pane_id, role)
        target = f"={spec.session_name}:team"
        self._run_checked(
            ("tmux", "select-layout", "-t", target, "tiled"),
            "select-layout",
        )
        self._run_checked(
            (
                "tmux",
                "set-option",
                "-w",
                "-t",
                target,
                "pane-border-status",
                "top",
            ),
            "pane-border-status",
        )
        self._run_checked(
            (
                "tmux",
                "set-option",
                "-w",
                "-t",
                target,
                "pane-border-format",
                " #{@atcode_role} ",
            ),
            "pane-border-format",
        )
        self._run_checked(
            ("tmux", "select-pane", "-t", f"={spec.session_name}:team.0"),
            "select-pane",
        )

    def _create_windows_session(self, spec: SessionSpec) -> None:
        by_role = {item.role: item for item in spec.roles}
        first = by_role[Role.PM]
        self._create_first_role(spec.session_name, Role.PM.value, first)
        self._set_role_metadata(
            f"={spec.session_name}:{Role.PM.value}.0",
            Role.PM,
        )
        for role in (Role.DEVELOPER, Role.REVIEWER):
            self._create_window(spec.session_name, by_role[role])
            self._set_role_metadata(
                f"={spec.session_name}:{role.value}.0",
                role,
            )
        self._run_checked(
            (
                "tmux",
                "select-window",
                "-t",
                f"={spec.session_name}:{Role.PM.value}",
            ),
            "select-window",
        )

    def _create_first_role(
        self,
        session_name: str,
        window_name: str,
        role_spec: RoleSpec,
    ) -> None:
        self._validate_identifier(window_name, "window")
        self._run_checked(
            (
                "tmux",
                "new-session",
                "-d",
                "-s",
                session_name,
                "-n",
                window_name,
                "-c",
                str(role_spec.cwd),
                self._launch_command(role_spec.launch),
            ),
            "new-session",
        )

    def _create_window(self, session_name: str, role_spec: RoleSpec) -> None:
        window_name = role_spec.role.value
        self._validate_identifier(window_name, "window")
        self._run_checked(
            (
                "tmux",
                "new-window",
                "-d",
                "-t",
                f"={session_name}",
                "-n",
                window_name,
                "-c",
                str(role_spec.cwd),
                self._launch_command(role_spec.launch),
            ),
            "new-window",
        )

    def _set_role_metadata(self, pane_target: str, role: Role) -> None:
        self._run_checked(
            (
                "tmux",
                "set-option",
                "-p",
                "-t",
                pane_target,
                "@atcode_role",
                role.value,
            ),
            "set-role-metadata",
        )

    @staticmethod
    def _detect_layout(endpoints: list[RoleEndpoint]) -> Layout | None:
        if not endpoints:
            return None
        if all(endpoint.window == "team" for endpoint in endpoints):
            return Layout.PANES
        if all(endpoint.window == endpoint.role.value for endpoint in endpoints):
            return Layout.WINDOWS
        return None

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
