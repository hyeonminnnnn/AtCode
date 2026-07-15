"""Project-root resolution and registration."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project
from atcode.ports.storage import ProjectStore

GitRootFinder = Callable[[Path], Path | None]


class ProjectService:
    def __init__(self, store: ProjectStore, git_root_finder: GitRootFinder) -> None:
        self._store = store
        self._git_root_finder = git_root_finder

    def resolve_root(self, explicit: str | Path | None, cwd: Path) -> Path:
        current = cwd.resolve()
        if explicit is not None:
            candidate = Path(explicit).expanduser()
            if not candidate.is_absolute():
                candidate = current / candidate
            return self._validate_root(candidate)

        registered = self._store.find_containing(current)
        if registered is not None:
            return self._validate_root(registered.root)

        git_root = self._git_root_finder(current)
        if git_root is not None:
            return self._validate_root(git_root)

        return self._validate_root(current)

    def init(self, explicit: str | Path | None, cwd: Path) -> Project:
        root = self.resolve_root(explicit, cwd)
        existing = self._store.find_by_root(root)
        if existing is not None:
            return existing

        project = Project(
            project_id=_project_id(root),
            name=root.name or "project",
            root=root,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._store.save(project)
        return project

    @staticmethod
    def _validate_root(candidate: Path) -> Path:
        root = candidate.resolve()
        if not root.is_dir():
            raise AtCodeError(
                "PROJECT_ROOT_INVALID",
                f"Project root is not a directory: {root}",
                hint="Choose an existing project directory.",
                exit_code=2,
            )
        return root


def _project_id(root: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:10]
    return f"{slug or 'project'}-{digest}"
