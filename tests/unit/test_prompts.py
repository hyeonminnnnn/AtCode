from __future__ import annotations

from pathlib import Path

import pytest

from atcode.application.prompts import PromptRenderer
from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project, Role
from atcode.infrastructure.storage.prompts import FilesystemPromptStore

REPO_ROOT = Path(__file__).resolve().parents[2]


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


@pytest.mark.parametrize("role", list(Role))
def test_role_template_has_operating_contract(role: Role) -> None:
    text = (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(
        encoding="utf-8"
    )

    for heading in (
        "## 핵심 책임",
        "## 작업 방법",
        "## 산출물",
        "## 완료 조건",
        "## 경계",
    ):
        assert heading in text
    assert "{{PROJECT_NAME}}" in text
    assert "{{PROJECT_ID}}" in text
    assert "{{PROJECT_ROOT}}" in text
    assert "{{ATCODE_HOME}}" in text
    assert "Phase 1" in text


def test_role_templates_embed_model_neutral_methods() -> None:
    templates = {
        role: (REPO_ROOT / "prompts" / f"{role.value}.md").read_text(
            encoding="utf-8"
        )
        for role in Role
    }

    pm = templates[Role.PM]
    reviewer = templates[Role.REVIEWER]

    assert "가정" in pm and "완료 조건" in pm
    assert "재작업" in pm and "최종 요약" in pm
    assert "사실" in pm and "명령" in pm and "경로" in pm and "한국어" in pm
    assert "실패하는 테스트" in templates[Role.DEVELOPER]
    assert "과설계" in reviewer
    assert "정상" in reviewer and "오류" in reviewer and "경계" in reviewer
    assert "회귀" in reviewer and "미검증" in reviewer
    assert "실행 명령" in reviewer and "실제 출력" in reviewer
    assert not any("$" in text for text in templates.values())


def test_prompt_directory_has_only_active_roles() -> None:
    assert {path.stem for path in (REPO_ROOT / "prompts").glob("*.md")} == {
        "pm",
        "developer",
        "reviewer",
    }
