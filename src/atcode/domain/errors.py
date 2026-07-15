"""Structured errors exposed by the AtCode application layer."""

from __future__ import annotations


class AtCodeError(Exception):
    """An expected Runtime error with a stable code and actionable hint."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.hint = hint
        self.exit_code = exit_code
