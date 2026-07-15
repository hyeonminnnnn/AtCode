"""Storage contracts used by application services."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from atcode.domain.models import Project


class ProjectStore(Protocol):
    def list(self) -> tuple[Project, ...]: ...

    def find_by_id(self, project_id: str) -> Project | None: ...

    def find_by_root(self, root: Path) -> Project | None: ...

    def find_containing(self, path: Path) -> Project | None: ...

    def save(self, project: Project) -> None: ...
