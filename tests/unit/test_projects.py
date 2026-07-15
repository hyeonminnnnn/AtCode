from __future__ import annotations

from pathlib import Path

import pytest

from atcode.application.projects import ProjectService
from atcode.domain.errors import AtCodeError
from atcode.infrastructure.storage.projects import JsonProjectStore


def make_service(runtime_home: Path, git_root: Path | None = None) -> ProjectService:
    store = JsonProjectStore(runtime_home / "projects")
    return ProjectService(store, git_root_finder=lambda _cwd: git_root)


def snapshot(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*")}


def test_non_git_project_uses_current_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    service = make_service(tmp_path / "runtime")

    assert service.resolve_root(None, target) == target.resolve()


def test_registered_parent_beats_nested_current_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    nested = target / "src" / "module"
    nested.mkdir(parents=True)
    service = make_service(tmp_path / "runtime")
    project = service.init(target, target)

    assert service.resolve_root(None, nested) == project.root


def test_git_root_is_used_for_unregistered_project(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    nested = target / "src"
    nested.mkdir(parents=True)
    service = make_service(tmp_path / "runtime", git_root=target)

    assert service.resolve_root(None, nested) == target.resolve()


def test_init_writes_only_under_atcode_home(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    runtime_home = tmp_path / "runtime"
    service = make_service(runtime_home)
    before = snapshot(target)

    project = service.init(target, target)

    assert snapshot(target) == before
    assert (
        runtime_home / "projects" / project.project_id / "project.json"
    ).is_file()


def test_repeated_init_preserves_existing_registration(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    service = make_service(tmp_path / "runtime")

    first = service.init(target, target)
    second = service.init(target, target)

    assert second == first


def test_explicit_missing_directory_is_rejected(tmp_path: Path) -> None:
    service = make_service(tmp_path / "runtime")

    with pytest.raises(AtCodeError, match="PROJECT_ROOT_INVALID"):
        service.resolve_root(tmp_path / "missing", tmp_path)
