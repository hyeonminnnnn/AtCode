from __future__ import annotations

from pathlib import Path

import pytest

from atcode.application.prompts import PromptRenderer
from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project, Role
from atcode.infrastructure.storage.prompts import FilesystemPromptStore


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    return Project("target-1234567890", "target", root, "2026-07-15T00:00:00Z")


def make_renderer(
    tmp_path: Path,
    template: str,
) -> tuple[PromptRenderer, Path]:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "developer.md").write_text(template, encoding="utf-8")
    runtime_home = tmp_path / "runtime"
    store = FilesystemPromptStore(templates, runtime_home)
    return PromptRenderer(store, runtime_home), runtime_home


def test_prompt_is_rendered_only_under_runtime_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    renderer, runtime_home = make_renderer(
        tmp_path,
        "# {{ROLE}}\nProject: {{PROJECT_ROOT}}\nHome: {{ATCODE_HOME}}\n",
    )
    before = set(project.root.rglob("*"))

    rendered = renderer.render(project, Role.DEVELOPER)

    assert rendered.path.is_relative_to(runtime_home)
    assert str(project.root) in rendered.text
    assert str(runtime_home.resolve()) in rendered.text
    assert set(project.root.rglob("*")) == before


def test_all_supported_tokens_are_replaced(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    renderer, _runtime_home = make_renderer(
        tmp_path,
        "{{PROJECT_NAME}}|{{PROJECT_ROOT}}|{{PROJECT_ID}}|{{ROLE}}|{{ATCODE_HOME}}",
    )

    rendered = renderer.render(project, Role.DEVELOPER)

    assert "{{" not in rendered.text
    assert rendered.text.startswith("target|")
    assert "|target-1234567890|developer|" in rendered.text


def test_unknown_template_token_fails(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    renderer, _runtime_home = make_renderer(tmp_path, "{{UNKNOWN_TOKEN}}")

    with pytest.raises(AtCodeError, match="PROMPT_TOKEN_UNKNOWN"):
        renderer.render(project, Role.DEVELOPER)
