"""JSON-backed project registration store."""

from __future__ import annotations

import re
from pathlib import Path

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project
from atcode.infrastructure.storage.json_file import read_json, write_json_atomic

_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]*-[0-9a-f]{10}$")


class JsonProjectStore:
    def __init__(self, projects_root: Path) -> None:
        self._root = projects_root

    def list(self) -> tuple[Project, ...]:
        if not self._root.is_dir():
            return ()
        paths = sorted(self._root.glob("*/project.json"))
        return tuple(self._load(path) for path in paths)

    def find_by_id(self, project_id: str) -> Project | None:
        self._validate_id(project_id)
        path = self._root / project_id / "project.json"
        return self._load(path) if path.is_file() else None

    def find_by_root(self, root: Path) -> Project | None:
        canonical = root.resolve()
        return next(
            (project for project in self.list() if project.root == canonical),
            None,
        )

    def find_containing(self, path: Path) -> Project | None:
        canonical = path.resolve()
        matches = [
            project
            for project in self.list()
            if canonical == project.root or canonical.is_relative_to(project.root)
        ]
        return max(matches, key=lambda project: len(project.root.parts), default=None)

    def save(self, project: Project) -> None:
        self._validate_id(project.project_id)
        write_json_atomic(
            self._root / project.project_id / "project.json",
            {
                "schemaVersion": 1,
                "projectId": project.project_id,
                "name": project.name,
                "root": str(project.root),
                "createdAt": project.created_at,
            },
        )

    @staticmethod
    def _validate_id(project_id: str) -> None:
        if not _PROJECT_ID.fullmatch(project_id):
            raise AtCodeError(
                "PROJECT_ID_INVALID",
                f"Invalid project ID: {project_id}",
            )

    @staticmethod
    def _load(path: Path) -> Project:
        try:
            value = read_json(path)
            if value.get("schemaVersion") != 1:
                raise ValueError("unsupported schemaVersion")
            root = Path(value["root"])
            if not root.is_absolute():
                raise ValueError("project root must be absolute")
            project = Project(
                project_id=value["projectId"],
                name=value["name"],
                root=root.resolve(),
                created_at=value["createdAt"],
            )
            JsonProjectStore._validate_id(project.project_id)
            return project
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "PROJECT_DATA_INVALID",
                f"Invalid project registration: {path}",
                hint="Repair or remove the Runtime project entry.",
            ) from error
