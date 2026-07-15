"""Filesystem storage for source and rendered role prompts."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project, RenderedPrompt, Role


class FilesystemPromptStore:
    def __init__(self, templates_root: Path, runtime_home: Path) -> None:
        self._templates = templates_root
        self._runtime_home = runtime_home.resolve()

    def read_template(self, role: Role) -> str:
        path = self._templates / f"{role.value}.md"
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise AtCodeError(
                "PROMPT_TEMPLATE_MISSING",
                f"Role prompt is unavailable: {path}",
            ) from error

    def write_rendered(
        self,
        project: Project,
        role: Role,
        text: str,
    ) -> RenderedPrompt:
        path = (
            self._runtime_home
            / "projects"
            / project.project_id
            / "workspace"
            / "prompts"
            / f"{role.value}.md"
        )
        _write_text_atomic(path, text)
        return RenderedPrompt(text=text, path=path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
