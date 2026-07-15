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
        values = {
            "PROJECT_NAME": project.name,
            "PROJECT_ROOT": str(project.root),
            "PROJECT_ID": project.project_id,
            "ROLE": role.value,
            "ATCODE_HOME": str(self._runtime_home),
        }
        unknown = sorted(set(_TOKEN.findall(template)) - set(values))
        if unknown:
            raise AtCodeError(
                "PROMPT_TOKEN_UNKNOWN",
                f"Unknown role prompt token: {unknown[0]}",
            )
        rendered = _TOKEN.sub(lambda match: values[match.group(1)], template)
        return self._store.write_rendered(project, role, rendered)
