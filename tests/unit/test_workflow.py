from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pytest

from atcode.application.handoffs import HandoffParser
from atcode.application.workflow import WorkflowService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    Layout,
    Project,
    Role,
    RoleEndpoint,
    SessionSnapshot,
    WorkflowState,
    WorkflowStatus,
)


class MemoryWorkflowStore:
    def __init__(self, workflow: WorkflowState | None = None) -> None:
        self.workflow = workflow or WorkflowState.initial()
        self.handoff: Handoff | None = None

    def read_workflow(self, _project: Project) -> WorkflowState:
        return self.workflow

    def write_workflow(self, _project: Project, state: WorkflowState) -> None:
        self.workflow = state

    def read_handoff(self, _project: Project) -> Handoff | None:
        return self.handoff

    def write_handoff(self, _project: Project, handoff: Handoff) -> None:
        self.handoff = handoff

    def delete_handoff(self, _project: Project) -> None:
        self.handoff = None


class FakeProjectLock:
    @contextmanager
    def locked(self, _project: Project):
        yield


class FakeBackend:
    def __init__(self, active_role: Role, output: str) -> None:
        panes = {Role.PM: "%1", Role.DEVELOPER: "%2", Role.REVIEWER: "%3"}
        self.snapshot = SessionSnapshot(
            "atcode-target-1234567890",
            True,
            Layout.PANES,
            tuple(
                RoleEndpoint(role, "team", pane, role is active_role)
                for role, pane in panes.items()
            ),
        )
        self.outputs = {active_role: output}
        self.read_roles: list[Role] = []
        self.deliveries: list[tuple[Role, str]] = []
        self.focused: Role | None = None
        self.fail_delivery = False
        self.fail_focus = False

    def inspect_session(self, _session_name: str) -> SessionSnapshot:
        return self.snapshot

    def read_role_output(self, _session_name: str, role: Role) -> str:
        self.read_roles.append(role)
        return self.outputs[role]

    def deliver_text(self, _session_name: str, role: Role, text: str) -> None:
        if self.fail_delivery:
            raise AtCodeError("TMUX_COMMAND_FAILED", "delivery failed")
        self.deliveries.append((role, text))

    def focus_role(self, _session_name: str, role: Role) -> None:
        if self.fail_focus:
            raise AtCodeError("TMUX_COMMAND_FAILED", "focus failed")
        self.focused = role


def make_project(tmp_path: Path) -> Project:
    target = tmp_path / "target"
    target.mkdir()
    return Project("target-1234567890", "target", target, "created")


def make_handoff(
    delivery: DeliveryState,
    *,
    transfer_id: int = 1,
) -> Handoff:
    return Handoff(
        transfer_id,
        Role.PM,
        Role.DEVELOPER,
        HandoffDecision.READY,
        delivery,
        "sha256:pending",
        "SUMMARY:\nbuild it",
        "2026-07-15T00:00:00+00:00",
        (
            "2026-07-15T00:00:01+00:00"
            if delivery is DeliveryState.DELIVERED
            else None
        ),
    )


def make_service(
    tmp_path: Path,
    active_role: Role,
    output: str,
    *,
    workflow: WorkflowState | None = None,
) -> tuple[WorkflowService, FakeBackend, MemoryWorkflowStore]:
    project = make_project(tmp_path)
    backend = FakeBackend(active_role, output)
    store = MemoryWorkflowStore(workflow)
    service = WorkflowService(
        project=project,
        session_name=f"atcode-{project.project_id}",
        backend=backend,
        parser=HandoffParser(),
        store=store,
        project_lock=FakeProjectLock(),
        clock=lambda: "2026-07-15T00:00:02+00:00",
    )
    return service, backend, store


def test_pm_handoff_moves_workflow_to_developer(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.PM,
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nbuild it\n</ATCODE_HANDOFF>",
    )

    result = service.next(source_pane="%1")

    assert result.from_role is Role.PM
    assert result.to_role is Role.DEVELOPER
    assert result.transfer_id == 1
    assert store.workflow.status is WorkflowStatus.ACTIVE
    assert store.workflow.current_role is Role.DEVELOPER
    assert store.workflow.round == 1
    assert store.handoff is not None
    assert store.handoff.delivery is DeliveryState.DELIVERED
    assert backend.deliveries[0][0] is Role.DEVELOPER
    assert backend.focused is Role.DEVELOPER


def test_reviewer_approval_completes_at_pm(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.REVIEWER,
        "<ATCODE_HANDOFF>\nSTATUS: approved\nSUMMARY:\nverified\n</ATCODE_HANDOFF>",
        workflow=WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.REVIEWER,
            1,
            2,
            {},
            "time",
        ),
    )

    service.next(source_pane="%3")

    assert store.workflow.status is WorkflowStatus.COMPLETE
    assert store.workflow.current_role is Role.PM
    assert backend.focused is Role.PM


def test_reviewer_rejection_then_pm_increments_round(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.REVIEWER,
        "<ATCODE_HANDOFF>\nSTATUS: rejected\nSUMMARY:\nfix test\n</ATCODE_HANDOFF>",
        workflow=WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.REVIEWER,
            1,
            2,
            {},
            "time",
        ),
    )
    service.next(source_pane="%3")
    backend.outputs[Role.PM] = (
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nrework\n</ATCODE_HANDOFF>"
    )
    backend.snapshot = SessionSnapshot(
        backend.snapshot.session_name,
        True,
        Layout.PANES,
        tuple(
            RoleEndpoint(item.role, item.window, item.pane, item.role is Role.PM)
            for item in backend.snapshot.endpoints
        ),
    )

    service.next(source_pane="%1")

    assert store.workflow.status is WorkflowStatus.ACTIVE
    assert store.workflow.current_role is Role.DEVELOPER
    assert store.workflow.round == 2


def test_wrong_source_pane_does_not_capture_or_advance(tmp_path: Path) -> None:
    service, backend, store = make_service(tmp_path, Role.PM, "unused")

    with pytest.raises(AtCodeError, match="WORKFLOW_ROLE_MISMATCH"):
        service.next(source_pane="%2")

    assert backend.read_roles == []
    assert store.workflow == WorkflowState.initial()


def test_duplicate_digest_is_rejected_without_delivery(tmp_path: Path) -> None:
    output = "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nsame\n</ATCODE_HANDOFF>"
    parsed = HandoffParser().parse(output, Role.PM)
    workflow = WorkflowState(
        WorkflowStatus.IDLE,
        Role.PM,
        0,
        1,
        {Role.PM: parsed.digest},
        "time",
    )
    service, backend, _store = make_service(
        tmp_path,
        Role.PM,
        output,
        workflow=workflow,
    )

    with pytest.raises(AtCodeError, match="HANDOFF_ALREADY_DELIVERED"):
        service.next(source_pane="%1")

    assert backend.deliveries == []


def test_pending_handoff_is_retried_without_recapture(tmp_path: Path) -> None:
    service, backend, store = make_service(tmp_path, Role.PM, "must not be read")
    store.handoff = make_handoff(DeliveryState.PENDING)

    service.next(source_pane="%1")

    assert backend.read_roles == []
    assert backend.deliveries[0][0] is Role.DEVELOPER
    assert store.handoff is not None
    assert store.handoff.delivery is DeliveryState.DELIVERED


def test_delivery_failure_keeps_pending_handoff_and_workflow(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.PM,
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nbuild it\n</ATCODE_HANDOFF>",
    )
    backend.fail_delivery = True

    with pytest.raises(AtCodeError, match="TMUX_COMMAND_FAILED"):
        service.next(source_pane="%1")

    assert store.handoff is not None
    assert store.handoff.delivery is DeliveryState.PENDING
    assert store.workflow == WorkflowState.initial()


def test_focus_failure_does_not_roll_back_delivered_workflow(tmp_path: Path) -> None:
    service, backend, store = make_service(
        tmp_path,
        Role.PM,
        "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nbuild it\n</ATCODE_HANDOFF>",
    )
    backend.fail_focus = True

    result = service.next(source_pane="%1")

    assert result.focus_warning == "focus failed"
    assert store.workflow.current_role is Role.DEVELOPER
    assert store.handoff is not None
    assert store.handoff.delivery is DeliveryState.DELIVERED


def test_delivered_handoff_ahead_of_workflow_is_reconciled(
    tmp_path: Path,
) -> None:
    service, _backend, store = make_service(tmp_path, Role.PM, "unused")
    store.handoff = make_handoff(DeliveryState.DELIVERED, transfer_id=1)

    state = service.reconcile()

    assert state.last_transfer_id == 1
    assert state.current_role is Role.DEVELOPER
