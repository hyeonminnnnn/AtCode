from __future__ import annotations

import json
from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    Layout,
    Lifecycle,
    Project,
    Role,
    RoleRuntime,
    RuntimeState,
)
from atcode.infrastructure.storage.state import JsonStateStore
from atcode.infrastructure.storage.lock import JsonProjectLock


def make_project(tmp_path: Path) -> Project:
    target = tmp_path / "target"
    target.mkdir()
    return Project("target-1234567890", "target", target, "created")


def make_state(project: Project) -> RuntimeState:
    return RuntimeState(
        project_id=project.project_id,
        backend="tmux",
        session_name=f"atcode-{project.project_id}",
        status=Lifecycle.RUNNING,
        started_at="2026-07-15T00:00:00Z",
        stopped_at=None,
        roles=tuple(RoleRuntime(role, "codex", role.value) for role in Role),
    )


def test_state_round_trip_stays_under_runtime_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonStateStore(runtime_home)
    state = make_state(project)

    store.write(project, state)

    assert store.read(project) == state
    assert not (project.root / "state.json").exists()
    assert (
        runtime_home / "projects" / project.project_id / "state.json"
    ).is_file()


def test_state_json_contains_no_prompt_or_user_task(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonStateStore(runtime_home)
    store.write(project, make_state(project))

    value = json.loads(
        (runtime_home / "projects" / project.project_id / "state.json").read_text()
    )

    assert "prompt" not in json.dumps(value).lower()
    assert "task" not in json.dumps(value).lower()


def test_state_writer_uses_schema_two_layout_and_endpoint(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonStateStore(runtime_home)

    store.write(project, make_state(project))

    value = json.loads(
        (runtime_home / "projects" / project.project_id / "state.json").read_text()
    )
    assert value["schemaVersion"] == 2
    assert value["layout"] == "panes"
    assert value["roles"][0]["endpoint"] == "pm"
    assert "window" not in value["roles"][0]


def test_legacy_roles_are_filtered_and_removed_on_next_write(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    path = runtime_home / "projects" / project.project_id / "state.json"
    path.parent.mkdir(parents=True)
    value = {
        "schemaVersion": 1,
        "projectId": project.project_id,
        "backend": "tmux",
        "backendSession": f"atcode-{project.project_id}",
        "status": "running",
        "startedAt": "2026-07-15T00:00:00Z",
        "stoppedAt": None,
        "roles": [
            {"role": name, "adapter": "codex", "window": name}
            for name in ("pm", "developer", "reviewer", "tester", "docs")
        ],
        "lastError": None,
    }
    path.write_text(json.dumps(value), encoding="utf-8")
    store = JsonStateStore(runtime_home)

    state = store.read(project)

    assert state is not None
    assert state.layout is Layout.WINDOWS
    assert tuple(item.role.value for item in state.roles) == (
        "pm",
        "developer",
        "reviewer",
    )
    assert json.loads(path.read_text(encoding="utf-8")) == value

    store.write(project, state)
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["schemaVersion"] == 2
    assert persisted["layout"] == "windows"
    assert [item["role"] for item in persisted["roles"]] == [
        "pm",
        "developer",
        "reviewer",
    ]


def test_unknown_role_in_state_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    path = runtime_home / "projects" / project.project_id / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "projectId": project.project_id,
                "backend": "tmux",
                "backendSession": f"atcode-{project.project_id}",
                "status": "running",
                "startedAt": None,
                "stoppedAt": None,
                "roles": [
                    {"role": "architect", "adapter": "codex", "window": "architect"}
                ],
                "lastError": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AtCodeError, match="STATE_INVALID"):
        JsonStateStore(runtime_home).read(project)


def test_unsupported_state_schema_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    path = runtime_home / "projects" / project.project_id / "state.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"schemaVersion": 99}', encoding="utf-8")

    with pytest.raises(AtCodeError, match="STATE_INVALID"):
        JsonStateStore(runtime_home).read(project)


def test_lock_file_is_created_under_runtime_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    lock = JsonProjectLock(runtime_home)

    with lock.locked(project):
        lock_path = runtime_home / "projects" / project.project_id / "state.lock"
        assert lock_path.is_file()


def test_state_for_a_different_project_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonStateStore(runtime_home)
    store.write(project, make_state(project))
    path = runtime_home / "projects" / project.project_id / "state.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["projectId"] = "other-0987654321"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(AtCodeError, match="STATE_INVALID"):
        store.read(project)
