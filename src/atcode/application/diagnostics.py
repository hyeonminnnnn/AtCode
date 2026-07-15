"""Read-only Runtime environment diagnostics."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

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
    ) -> None:
        self._paths = paths
        self._configuration = configuration
        self._adapters = adapters
        self._backend = backend
        self._prompts = prompts
        self._state_store = state_store

    def run(self, project: Project | None) -> tuple[DiagnosticResult, ...]:
        backend_result = self._backend.probe()
        results = [self._python(), self._platform(), self._home(), backend_result]

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
        return tuple(results)

    def _state_session(self, project: Project) -> DiagnosticResult:
        try:
            state = self._state_store.read(project)
            snapshot = self._backend.inspect_session(
                f"atcode-{project.project_id}"
            )
        except AtCodeError as error:
            return DiagnosticResult(
                "state/session",
                DiagnosticLevel.FAIL,
                error.message,
                error.hint,
            )

        if not snapshot.exists:
            actual = Lifecycle.STOPPED
        elif {role.value for role in Role}.issubset(snapshot.windows):
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
        return DiagnosticResult(
            "state/session",
            level,
            message,
            None if level is DiagnosticLevel.PASS else "Run atcode status to reconcile state.",
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
