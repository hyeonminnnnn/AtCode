"""Contract implemented by each supported AI CLI Adapter."""

from __future__ import annotations

from typing import Protocol

from atcode.domain.models import DiagnosticResult, LaunchSpec, RoleLaunchContext


class AgentAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def probe(self) -> DiagnosticResult: ...

    def build_launch(self, context: RoleLaunchContext) -> LaunchSpec: ...
