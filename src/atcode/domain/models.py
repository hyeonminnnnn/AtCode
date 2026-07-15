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


class DiagnosticLevel(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    level: DiagnosticLevel
    message: str
    hint: str | None = None

    @property
    def ok(self) -> bool:
        return self.level is not DiagnosticLevel.FAIL


@dataclass(frozen=True)
class RoleLaunchContext:
    project: Project
    role: Role
    prompt: RenderedPrompt
    atcode_home: Path


@dataclass(frozen=True)
class LaunchSpec:
    executable: str
    arguments: tuple[str, ...] = ()
    environment: Mapping[str, str] | None = None
