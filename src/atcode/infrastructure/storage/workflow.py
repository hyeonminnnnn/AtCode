"""Atomic persistence for the current workflow and latest handoff."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from atcode.infrastructure.storage.json_file import read_json, write_json_atomic

_WORKFLOW_KEYS = {
    "schemaVersion",
    "status",
    "currentRole",
    "round",
    "lastTransferId",
    "lastDigests",
    "updatedAt",
}
_HANDOFF_KEYS = {
    "schemaVersion",
    "transferId",
    "fromRole",
    "toRole",
    "decision",
    "delivery",
    "digest",
    "body",
    "createdAt",
    "deliveredAt",
}


class JsonWorkflowStore:
    def __init__(self, runtime_home: Path) -> None:
        self._home = runtime_home

    def read_workflow(self, project: Project) -> WorkflowState:
        path = self._workflow_path(project)
        if not path.is_file():
            return WorkflowState.initial()
        try:
            value = read_json(path)
            _require_exact(value, _WORKFLOW_KEYS)
            if value["schemaVersion"] != 1:
                raise ValueError("unsupported workflow schemaVersion")
            round_number = _non_negative_int(value["round"], "round")
            transfer_id = _non_negative_int(
                value["lastTransferId"], "lastTransferId"
            )
            raw_digests = value["lastDigests"]
            if not isinstance(raw_digests, dict):
                raise ValueError("lastDigests must be an object")
            digests = {Role(key): _string(item, key) for key, item in raw_digests.items()}
            updated_at = value["updatedAt"]
            if updated_at is not None:
                updated_at = _string(updated_at, "updatedAt")
            return WorkflowState(
                status=WorkflowStatus(value["status"]),
                current_role=Role(value["currentRole"]),
                round=round_number,
                last_transfer_id=transfer_id,
                last_digests=digests,
                updated_at=updated_at,
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "WORKFLOW_INVALID",
                f"Workflow state is invalid: {path}",
                hint="Repair or remove the Runtime workflow.json file.",
            ) from error

    def write_workflow(self, project: Project, state: WorkflowState) -> None:
        write_json_atomic(
            self._workflow_path(project),
            {
                "schemaVersion": 1,
                "status": state.status.value,
                "currentRole": state.current_role.value,
                "round": state.round,
                "lastTransferId": state.last_transfer_id,
                "lastDigests": {
                    role.value: digest for role, digest in state.last_digests.items()
                },
                "updatedAt": state.updated_at,
            },
        )

    def read_handoff(self, project: Project) -> Handoff | None:
        path = self._handoff_path(project)
        if not path.is_file():
            return None
        try:
            value = read_json(path)
            _require_exact(value, _HANDOFF_KEYS)
            if value["schemaVersion"] != 1:
                raise ValueError("unsupported handoff schemaVersion")
            transfer_id = _positive_int(value["transferId"], "transferId")
            from_role = Role(value["fromRole"])
            to_role = Role(value["toRole"])
            if from_role is to_role:
                raise ValueError("handoff roles must differ")
            body = _string(value["body"], "body")
            if not body or len(body.encode("utf-8")) > 32 * 1024:
                raise ValueError("invalid handoff body")
            delivered_at = value["deliveredAt"]
            if delivered_at is not None:
                delivered_at = _string(delivered_at, "deliveredAt")
            return Handoff(
                transfer_id=transfer_id,
                from_role=from_role,
                to_role=to_role,
                decision=HandoffDecision(value["decision"]),
                delivery=DeliveryState(value["delivery"]),
                digest=_string(value["digest"], "digest"),
                body=body,
                created_at=_string(value["createdAt"], "createdAt"),
                delivered_at=delivered_at,
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "HANDOFF_INVALID",
                f"Handoff state is invalid: {path}",
                hint="Repair or remove the Runtime handoff.json file.",
            ) from error

    def write_handoff(self, project: Project, handoff: Handoff) -> None:
        write_json_atomic(
            self._handoff_path(project),
            {
                "schemaVersion": 1,
                "transferId": handoff.transfer_id,
                "fromRole": handoff.from_role.value,
                "toRole": handoff.to_role.value,
                "decision": handoff.decision.value,
                "delivery": handoff.delivery.value,
                "digest": handoff.digest,
                "body": handoff.body,
                "createdAt": handoff.created_at,
                "deliveredAt": handoff.delivered_at,
            },
        )

    def delete_handoff(self, project: Project) -> None:
        self._handoff_path(project).unlink(missing_ok=True)

    def _workspace(self, project: Project) -> Path:
        return self._home / "projects" / project.project_id / "workspace"

    def _workflow_path(self, project: Project) -> Path:
        return self._workspace(project) / "workflow.json"

    def _handoff_path(self, project: Project) -> Path:
        return self._workspace(project) / "handoff.json"


def _require_exact(value: dict[str, Any], keys: set[str]) -> None:
    if set(value) != keys:
        raise ValueError("unexpected JSON fields")


def _non_negative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _positive_int(value: Any, name: str) -> int:
    result = _non_negative_int(value, name)
    if result == 0:
        raise ValueError(f"{name} must be positive")
    return result


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value
