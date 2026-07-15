"""Codex CLI Adapter."""

from __future__ import annotations

from shutil import which

from atcode.domain.models import DiagnosticResult, LaunchSpec, RoleLaunchContext
from atcode.infrastructure.adapters.common import (
    ExecutableFinder,
    launch_environment,
    probe_executable,
)


class CodexAdapter:
    name = "codex"

    def __init__(self, finder: ExecutableFinder = which) -> None:
        self._finder = finder

    def probe(self) -> DiagnosticResult:
        return probe_executable(self.name, "codex", self._finder)

    def build_launch(self, context: RoleLaunchContext) -> LaunchSpec:
        return LaunchSpec(
            "codex",
            (context.prompt.text,),
            launch_environment(context),
        )
