"""Interactive login-shell Adapter."""

from __future__ import annotations

from collections.abc import Mapping
from shutil import which

from atcode.domain.models import DiagnosticResult, LaunchSpec, RoleLaunchContext
from atcode.infrastructure.adapters.common import (
    ExecutableFinder,
    launch_environment,
    probe_executable,
)


class ShellAdapter:
    name = "shell"

    def __init__(
        self,
        env: Mapping[str, str],
        finder: ExecutableFinder = which,
    ) -> None:
        self._executable = env.get("SHELL") or "/bin/bash"
        self._finder = finder

    def probe(self) -> DiagnosticResult:
        return probe_executable(self.name, self._executable, self._finder)

    def build_launch(self, context: RoleLaunchContext) -> LaunchSpec:
        return LaunchSpec(
            self._executable,
            ("-l",),
            launch_environment(context),
        )
