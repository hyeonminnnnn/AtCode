from __future__ import annotations

from pathlib import Path

import pytest

from atcode.application.configuration import ConfigurationService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project, Role
from atcode.infrastructure.storage.configuration import JsonConfigurationStore


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    return Project("target-1234567890", "target", root, "2026-07-15T00:00:00Z")


def make_service(tmp_path: Path) -> tuple[ConfigurationService, JsonConfigurationStore]:
    store = JsonConfigurationStore(tmp_path / "runtime")
    service = ConfigurationService(
        store,
        allowed_backends={"tmux"},
        allowed_adapters={"codex", "claude", "gemini", "shell"},
    )
    return service, store


def test_project_role_override_wins(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_global(
        {"schemaVersion": 1, "roles": {"reviewer": {"adapter": "gemini"}}}
    )
    store.write_project(
        project,
        {"schemaVersion": 1, "roles": {"reviewer": {"adapter": "codex"}}},
    )

    config = service.effective(project)

    assert config.roles[Role.REVIEWER].adapter == "codex"
    assert config.roles[Role.DEVELOPER].adapter == "codex"


def test_global_override_applies_without_project_override(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)

    service.set(project, "roles.docs.adapter", "shell", global_scope=True)

    assert service.effective(project).roles[Role.DOCS].adapter == "shell"


def test_unknown_role_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)

    with pytest.raises(AtCodeError, match="CONFIG_KEY_INVALID"):
        service.set(
            project,
            "roles.architect.adapter",
            "codex",
            global_scope=False,
        )


def test_unknown_adapter_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)

    with pytest.raises(AtCodeError, match="CONFIG_VALUE_INVALID"):
        service.set(project, "roles.pm.adapter", "unknown", global_scope=False)


def test_unset_project_value_reveals_global_value(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)
    service.set(project, "roles.tester.adapter", "shell", global_scope=True)
    service.set(project, "roles.tester.adapter", "gemini", global_scope=False)

    service.unset(project, "roles.tester.adapter", global_scope=False)

    assert service.get(project, "roles.tester.adapter") == "shell"


def test_unknown_json_key_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_project(project, {"schemaVersion": 1, "extra": True})

    with pytest.raises(AtCodeError, match="CONFIG_INVALID"):
        service.effective(project)


@pytest.mark.parametrize("operation", ["set", "unset"])
def test_mutation_reports_structured_error_for_malformed_json(
    tmp_path: Path,
    operation: str,
) -> None:
    project = make_project(tmp_path)
    service, _store = make_service(tmp_path)
    path = tmp_path / "runtime" / "projects" / project.project_id / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")

    with pytest.raises(AtCodeError, match="CONFIG_INVALID"):
        if operation == "set":
            service.set(
                project,
                "roles.pm.adapter",
                "codex",
                global_scope=False,
            )
        else:
            service.unset(project, "roles.pm.adapter", global_scope=False)
