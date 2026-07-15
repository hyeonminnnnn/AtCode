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


def test_all_default_roles_use_codex(tmp_path: Path) -> None:
    service, _store = make_service(tmp_path)

    config = service.effective(None)

    assert {role: config.roles[role].adapter for role in Role} == {
        role: "codex" for role in Role
    }


def test_phase_one_has_exactly_three_roles() -> None:
    assert tuple(role.value for role in Role) == ("pm", "developer", "reviewer")


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

    service.set(project, "roles.developer.adapter", "shell", global_scope=True)

    assert service.effective(project).roles[Role.DEVELOPER].adapter == "shell"


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
    service.set(project, "roles.developer.adapter", "shell", global_scope=True)
    service.set(project, "roles.developer.adapter", "gemini", global_scope=False)

    service.unset(project, "roles.developer.adapter", global_scope=False)

    assert service.get(project, "roles.developer.adapter") == "shell"


def test_legacy_roles_are_ignored_without_mutating_file(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    stored = {
        "schemaVersion": 1,
        "roles": {
            "reviewer": {"adapter": "gemini"},
            "tester": {"adapter": "codex"},
            "docs": {"adapter": "claude"},
        },
    }
    store.write_project(project, stored)

    config = service.effective(project)

    assert set(config.roles) == {Role.PM, Role.DEVELOPER, Role.REVIEWER}
    assert config.roles[Role.REVIEWER].adapter == "gemini"
    assert store.read_project(project) == stored


def test_next_config_write_removes_legacy_roles(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_project(
        project,
        {
            "schemaVersion": 1,
            "roles": {
                "tester": {"adapter": "codex"},
                "docs": {"adapter": "codex"},
            },
        },
    )

    service.set(project, "roles.reviewer.adapter", "gemini", global_scope=False)

    assert store.read_project(project) == {
        "schemaVersion": 1,
        "roles": {"reviewer": {"adapter": "gemini"}},
    }


def test_unknown_persisted_role_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_project(
        project,
        {"schemaVersion": 1, "roles": {"architect": {"adapter": "codex"}}},
    )

    with pytest.raises(AtCodeError, match="CONFIG_INVALID"):
        service.effective(project)


@pytest.mark.parametrize("role_name", ["tester", "docs"])
def test_malformed_legacy_role_is_rejected(
    tmp_path: Path,
    role_name: str,
) -> None:
    project = make_project(tmp_path)
    service, store = make_service(tmp_path)
    store.write_project(
        project,
        {"schemaVersion": 1, "roles": {role_name: {}}},
    )

    with pytest.raises(AtCodeError, match="CONFIG_INVALID"):
        service.effective(project)


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
