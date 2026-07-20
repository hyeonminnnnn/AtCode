"""Storage contracts used by application services."""

from __future__ import annotations

from pathlib import Path
from contextlib import AbstractContextManager
from typing import Any, Protocol

from atcode.domain.models import (
    Handoff,
    Project,
    RenderedPrompt,
    Role,
    RuntimeState,
    WorkflowState,
)


class ProjectStore(Protocol):
    def list(self) -> tuple[Project, ...]: ...

    def find_by_id(self, project_id: str) -> Project | None: ...

    def find_by_root(self, root: Path) -> Project | None: ...

    def find_containing(self, path: Path) -> Project | None: ...

    def save(self, project: Project) -> None: ...


class ConfigurationStore(Protocol):
    def read_global(self) -> dict[str, Any]: ...

    def write_global(self, value: dict[str, Any]) -> None: ...

    def read_project(self, project: Project) -> dict[str, Any]: ...

    def write_project(self, project: Project, value: dict[str, Any]) -> None: ...


class PromptStore(Protocol):
    def read_template(self, role: Role) -> str: ...

    def write_rendered(
        self,
        project: Project,
        role: Role,
        text: str,
    ) -> RenderedPrompt: ...


class StateStore(Protocol):
    def read(self, project: Project) -> RuntimeState | None: ...

    def write(self, project: Project, state: RuntimeState) -> None: ...


class ProjectLock(Protocol):
    def locked(self, project: Project) -> AbstractContextManager[None]: ...


class WorkflowStore(Protocol):
    def read_workflow(self, project: Project) -> WorkflowState: ...

    def write_workflow(self, project: Project, state: WorkflowState) -> None: ...

    def read_handoff(self, project: Project) -> Handoff | None: ...

    def write_handoff(self, project: Project, handoff: Handoff) -> None: ...

    def delete_handoff(self, project: Project) -> None: ...
