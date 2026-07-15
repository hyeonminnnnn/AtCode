"""Explicit Registry for built-in Phase 1 Adapters."""

from __future__ import annotations

from collections.abc import Iterable

from atcode.domain.errors import AtCodeError
from atcode.ports.adapter import AgentAdapter


class AdapterRegistry:
    def __init__(self, adapters: Iterable[AgentAdapter]) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._adapters)

    def get(self, name: str) -> AgentAdapter:
        try:
            return self._adapters[name]
        except KeyError as error:
            raise AtCodeError(
                "ADAPTER_UNKNOWN",
                f"Unknown Adapter: {name}",
                exit_code=2,
            ) from error
