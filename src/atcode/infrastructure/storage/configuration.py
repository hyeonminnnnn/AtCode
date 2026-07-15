"""Global and project JSON configuration storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from atcode.domain.models import Project
from atcode.infrastructure.storage.json_file import read_json, write_json_atomic


class JsonConfigurationStore:
    def __init__(self, runtime_home: Path) -> None:
        self._home = runtime_home

    def read_global(self) -> dict[str, Any]:
        return self._read_or_default(self._home / "config.json")

    def write_global(self, value: dict[str, Any]) -> None:
        write_json_atomic(self._home / "config.json", value)

    def read_project(self, project: Project) -> dict[str, Any]:
        return self._read_or_default(self._project_path(project))

    def write_project(self, project: Project, value: dict[str, Any]) -> None:
        write_json_atomic(self._project_path(project), value)

    def _project_path(self, project: Project) -> Path:
        return self._home / "projects" / project.project_id / "config.json"

    @staticmethod
    def _read_or_default(path: Path) -> dict[str, Any]:
        return read_json(path) if path.is_file() else {"schemaVersion": 1}
