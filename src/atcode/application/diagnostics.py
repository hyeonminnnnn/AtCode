"""Read-only Runtime environment diagnostics."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atcode.application.workflow import reconcile_state
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    Lifecycle,
    Project,
    Role,
)


class DiagnosticsService:
    def __init__(
        self,
        *,
        paths: Any,
        configuration: Any,
        adapters: Any,
        backend: Any,
        prompts: Any,
        state_store: Any,
        workflow_store: Any,
        project_lock: Any,
    ) -> None:
        self._paths = paths
        self._configuration = configuration
        self._adapters = adapters
        self._backend = backend
        self._prompts = prompts
        self._state_store = state_store
        self._workflow_store = workflow_store
        self._project_lock = project_lock

    def run(self, project: Project | None) -> tuple[DiagnosticResult, ...]:
        backend_result = self._backend.probe()
        results = [self._python(), self._platform(), self._home(), backend_result]
        if backend_result.ok:
            try:
                results.append(self._backend.next_action_probe())
            except AtCodeError as error:
                results.append(
                    DiagnosticResult(
                        "next-action",
                        DiagnosticLevel.FAIL,
                        error.message,
                        error.hint,
                    )
                )

        try:
            config = self._configuration.effective(project)
            results.append(
                DiagnosticResult("config", DiagnosticLevel.PASS, "valid")
            )
            for adapter_name in sorted(
                {item.adapter for item in config.roles.values()}
            ):
                results.append(self._adapters.get(adapter_name).probe())
        except AtCodeError as error:
            results.append(
                DiagnosticResult(
                    "config",
                    DiagnosticLevel.FAIL,
                    error.message,
                    error.hint,
                )
            )

        try:
            self._prompts.validate_templates()
            results.append(
                DiagnosticResult("prompts", DiagnosticLevel.PASS, "valid")
            )
        except AtCodeError as error:
            results.append(
                DiagnosticResult(
                    "prompts",
                    DiagnosticLevel.FAIL,
                    error.message,
                    error.hint,
                )
            )

        if project is not None:
            root_exists = project.root.is_dir()
            results.append(
                DiagnosticResult(
                    "project",
                    DiagnosticLevel.PASS if root_exists else DiagnosticLevel.FAIL,
                    str(project.root),
                    None if root_exists else "Register the project's current path.",
                )
            )
            if backend_result.ok:
                results.append(self._state_session(project))
            results.append(self._workflow(project))
        return tuple(results)

    def _workflow(self, project: Project) -> DiagnosticResult:
        try:
            with self._project_lock.locked(project):
                state = self._workflow_store.read_workflow(project)
                handoff = self._workflow_store.read_handoff(project)
                reconciled = reconcile_state(
                    state,
                    handoff,
                    datetime.now(timezone.utc).isoformat(),
                )
        except AtCodeError as error:
            return DiagnosticResult(
                "workflow",
                DiagnosticLevel.FAIL,
                error.message,
                error.hint,
            )

        message = (
            f"{state.status.value}; role={state.current_role.value}; "
            f"round={state.round}; transfer={state.last_transfer_id}"
        )
        if reconciled != state:
            return DiagnosticResult(
                "workflow",
                DiagnosticLevel.WARN,
                message + "; delivered handoff is awaiting reconciliation",
                "Run atcode status to reconcile Runtime state.",
            )
        return DiagnosticResult(
            "workflow",
            DiagnosticLevel.PASS,
            message,
        )

    def _state_session(self, project: Project) -> DiagnosticResult:
        try:
            state = self._state_store.read(project)
            snapshot = self._backend.inspect_session(
                f"atcode-{project.project_id}"
            )
            expected_layout = self._configuration.effective(project).layout
        except AtCodeError as error:
            return DiagnosticResult(
                "state/session",
                DiagnosticLevel.FAIL,
                error.message,
                error.hint,
            )

        if not snapshot.exists:
            actual = Lifecycle.STOPPED
        elif (
            {endpoint.role for endpoint in snapshot.endpoints} == set(Role)
            and len(snapshot.endpoints) == len(Role)
            and snapshot.layout is expected_layout
        ):
            actual = Lifecycle.RUNNING
        else:
            actual = Lifecycle.DEGRADED

        if state is None:
            level = (
                DiagnosticLevel.PASS
                if actual is Lifecycle.STOPPED
                else DiagnosticLevel.WARN
            )
            message = f"no stored state; tmux={actual.value}"
        else:
            level = (
                DiagnosticLevel.PASS
                if state.status is actual
                else DiagnosticLevel.WARN
            )
            message = f"stored={state.status.value}; tmux={actual.value}"
        if snapshot.exists:
            roles = ", ".join(
                role.value
                for role in Role
                if role in {item.role for item in snapshot.endpoints}
            )
            layout = (
                snapshot.layout.value
                if snapshot.layout is not None
                else "unknown"
            )
            message += f"; layout={layout}; roles={roles or 'none'}"
        return DiagnosticResult(
            "state/session",
            level,
            message,
            (
                None
                if level is DiagnosticLevel.PASS
                else "Run atcode status to reconcile state."
            ),
        )

    @staticmethod
    def _python() -> DiagnosticResult:
        supported = sys.version_info >= (3, 11)
        return DiagnosticResult(
            "python",
            DiagnosticLevel.PASS if supported else DiagnosticLevel.FAIL,
            sys.version.split()[0],
            None if supported else "Install Python 3.11 or newer.",
        )

    @staticmethod
    def _platform() -> DiagnosticResult:
        supported = sys.platform.startswith("linux")
        return DiagnosticResult(
            "platform",
            DiagnosticLevel.PASS if supported else DiagnosticLevel.FAIL,
            sys.platform,
            None if supported else "Run AtCode inside WSL2 or Linux.",
        )

    def _home(self) -> DiagnosticResult:
        candidate = self._paths.home
        existing = candidate
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        writable = existing.is_dir() and os.access(existing, os.W_OK)
        return DiagnosticResult(
            "ATCODE_HOME",
            DiagnosticLevel.PASS if writable else DiagnosticLevel.FAIL,
            str(candidate),
            None if writable else "Choose a writable absolute ATCODE_HOME.",
        )
