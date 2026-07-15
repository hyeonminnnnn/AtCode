"""Read-only Runtime environment diagnostics."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from atcode.domain.models import DiagnosticLevel, DiagnosticResult, Project


class DiagnosticsService:
    def __init__(
        self,
        *,
        paths: Any,
        configuration: Any,
        adapters: Any,
        backend: Any,
    ) -> None:
        self._paths = paths
        self._configuration = configuration
        self._adapters = adapters
        self._backend = backend

    def run(self, project: Project | None) -> tuple[DiagnosticResult, ...]:
        results = [self._python(), self._platform(), self._home(), self._backend.probe()]
        config = self._configuration.effective(project)
        for adapter_name in sorted({item.adapter for item in config.roles.values()}):
            results.append(self._adapters.get(adapter_name).probe())
        if project is not None:
            results.append(
                DiagnosticResult(
                    "project",
                    DiagnosticLevel.PASS,
                    str(project.root),
                )
            )
        return tuple(results)

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
