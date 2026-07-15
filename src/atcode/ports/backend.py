"""Terminal Backend contract for Phase 1 session lifecycle."""

from __future__ import annotations

from typing import Protocol

from atcode.domain.models import DiagnosticResult, SessionSnapshot, SessionSpec


class TerminalBackend(Protocol):
    def probe(self) -> DiagnosticResult: ...

    def session_exists(self, session_name: str) -> bool: ...

    def create_session(self, spec: SessionSpec) -> None: ...

    def inspect_session(self, session_name: str) -> SessionSnapshot: ...

    def attach_session(self, session_name: str) -> None: ...

    def terminate_session(self, session_name: str) -> None: ...
