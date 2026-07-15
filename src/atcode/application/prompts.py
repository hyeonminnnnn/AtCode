"""Role prompt rendering with an intentionally small token language."""

from __future__ import annotations

import re
from pathlib import Path

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project, RenderedPrompt, Role
from atcode.ports.storage import PromptStore

_TOKEN = re.compile(r"{{([^{}]+)}}")


class PromptRenderer:
    def __init__(self, store: PromptStore, runtime_home: Path) -> None:
        self._store = store
        self._runtime_home = runtime_home.resolve()

    def render(self, project: Project, role: Role) -> RenderedPrompt:
        template = self._store.read_template(role)
        self._validate_template(template)
        values = {
            "PROJECT_NAME": project.name,
            "PROJECT_ROOT": str(project.root),
            "PROJECT_ID": project.project_id,
            "ROLE": role.value,
            "ATCODE_HOME": str(self._runtime_home),
        }
        rendered = _TOKEN.sub(lambda match: values[match.group(1)], template)
        return self._store.write_rendered(project, role, rendered)

    def validate_templates(self) -> None:
        """Validate source templates without rendering or writing files."""

        for role in Role:
            self._validate_template(self._store.read_template(role))

    @staticmethod
    def _validate_template(template: str) -> None:
        allowed = {
            "PROJECT_NAME",
            "PROJECT_ROOT",
            "PROJECT_ID",
            "ROLE",
            "ATCODE_HOME",
        }
        unknown = sorted(set(_TOKEN.findall(template)) - allowed)
        if unknown:
            raise AtCodeError(
                "PROMPT_TOKEN_UNKNOWN",
                f"Unknown role prompt token: {unknown[0]}",
            )
