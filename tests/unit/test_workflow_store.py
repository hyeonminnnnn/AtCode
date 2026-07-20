from __future__ import annotations

import json
from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    Project,
    Role,
    WorkflowState,
    WorkflowStatus,
)
from atcode.infrastructure.storage.workflow import JsonWorkflowStore


def make_project(tmp_path: Path) -> Project:
    root = tmp_path / "target"
    root.mkdir()
    return Project("target-1234567890", "target", root, "created")


def make_handoff(body: str = "SUMMARY:\nwork") -> Handoff:
    return Handoff(
        transfer_id=1,
        from_role=Role.PM,
        to_role=Role.DEVELOPER,
        decision=HandoffDecision.READY,
        delivery=DeliveryState.DELIVERED,
        digest="sha256:abc",
        body=body,
        created_at="2026-07-15T00:00:00+00:00",
        delivered_at="2026-07-15T00:00:01+00:00",
    )


def test_missing_workflow_reads_as_idle_pm(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    store = JsonWorkflowStore(tmp_path / "runtime")

    assert store.read_workflow(project) == WorkflowState.initial()


def test_workflow_and_handoff_round_trip_under_runtime_home(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonWorkflowStore(runtime_home)
    workflow = WorkflowState(
        WorkflowStatus.ACTIVE,
        Role.DEVELOPER,
        1,
        1,
        {Role.PM: "sha256:abc"},
        "2026-07-15T00:00:01+00:00",
    )

    store.write_workflow(project, workflow)
    store.write_handoff(project, make_handoff())

    assert store.read_workflow(project) == workflow
    assert store.read_handoff(project) == make_handoff()
    assert not (project.root / "workflow.json").exists()
    assert not (project.root / "handoff.json").exists()


def test_next_handoff_replaces_previous_file(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    runtime_home = tmp_path / "runtime"
    store = JsonWorkflowStore(runtime_home)

    store.write_handoff(project, make_handoff("SUMMARY:\nfirst"))
    store.write_handoff(project, make_handoff("SUMMARY:\nsecond"))

    handoff = store.read_handoff(project)
    assert handoff is not None
    assert handoff.body == "SUMMARY:\nsecond"
    workspace = runtime_home / "projects" / project.project_id / "workspace"
    assert {path.name for path in workspace.iterdir()} == {"handoff.json"}


def test_delete_handoff_is_idempotent(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    store = JsonWorkflowStore(tmp_path / "runtime")
    store.write_handoff(project, make_handoff())

    store.delete_handoff(project)
    store.delete_handoff(project)

    assert store.read_handoff(project) is None


def test_invalid_workflow_json_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    path = (
        tmp_path
        / "runtime"
        / "projects"
        / project.project_id
        / "workspace"
        / "workflow.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")

    with pytest.raises(AtCodeError, match="WORKFLOW_INVALID"):
        JsonWorkflowStore(tmp_path / "runtime").read_workflow(project)
