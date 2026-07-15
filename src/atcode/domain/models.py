"""Domain value objects shared by application services and ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Project:
    """A target project registered outside its own root."""

    project_id: str
    name: str
    root: Path
    created_at: str


class Role(str, Enum):
    PM = "pm"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DOCS = "docs"


@dataclass(frozen=True)
class RoleAssignment:
    adapter: str


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str
    roles: Mapping[Role, RoleAssignment]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "backend": self.backend,
            "roles": {
                role.value: {"adapter": self.roles[role].adapter} for role in Role
            },
        }


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    path: Path
