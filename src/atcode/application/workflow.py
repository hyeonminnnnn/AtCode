"""Fixed PM -> Developer -> Reviewer relay workflow coordination."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable

from atcode.application.handoffs import HandoffParser
from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DeliveryState,
    Handoff,
    HandoffDecision,
    Project,
    Role,
    SessionSnapshot,
    TransferResult,
    WorkflowState,
    WorkflowStatus,
)
from atcode.ports.backend import TerminalBackend
from atcode.ports.storage import ProjectLock, WorkflowStore

_NEXT_ROLE = {
    Role.PM: Role.DEVELOPER,
    Role.DEVELOPER: Role.REVIEWER,
    Role.REVIEWER: Role.PM,
}


def transition(
    state: WorkflowState,
    source: Role,
    decision: HandoffDecision,
    transfer_id: int,
    digest: str,
    now: str,
) -> WorkflowState:
    digests = dict(state.last_digests)
    digests[source] = digest
    if source is Role.PM:
        round_number = (
            state.round + 1 if state.status is WorkflowStatus.REWORK else 1
        )
        return WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.DEVELOPER,
            round_number,
            transfer_id,
            digests,
            now,
        )
    if source is Role.DEVELOPER:
        return WorkflowState(
            WorkflowStatus.ACTIVE,
            Role.REVIEWER,
            state.round,
            transfer_id,
            digests,
            now,
        )
    status = (
        WorkflowStatus.COMPLETE
        if decision is HandoffDecision.APPROVED
        else WorkflowStatus.REWORK
    )
    return WorkflowState(
        status,
        Role.PM,
        state.round,
        transfer_id,
        digests,
        now,
    )


def reconcile_state(
    state: WorkflowState,
    handoff: Handoff | None,
    now: str,
) -> WorkflowState:
    if (
        handoff is None
        or handoff.delivery is not DeliveryState.DELIVERED
        or handoff.transfer_id <= state.last_transfer_id
    ):
        return state
    return transition(
        state,
        handoff.from_role,
        handoff.decision,
        handoff.transfer_id,
        handoff.digest,
        handoff.delivered_at or now,
    )


def transfer_text(handoff: Handoff) -> str:
    return (
        f"[ATCODE_TRANSFER id={handoff.transfer_id} "
        f"from={handoff.from_role.value} to={handoff.to_role.value}]\n"
        f"{handoff.body}"
    )


class WorkflowService:
    def __init__(
        self,
        *,
        project: Project,
        session_name: str,
        backend: TerminalBackend,
        parser: HandoffParser,
        store: WorkflowStore,
        project_lock: ProjectLock,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._project = project
        self._session_name = session_name
        self._backend = backend
        self._parser = parser
        self._store = store
        self._project_lock = project_lock
        self._clock = clock or _utc_now

    def current(self) -> WorkflowState:
        return self.reconcile()

    def reconcile(self) -> WorkflowState:
        with self._project_lock.locked(self._project):
            return self._reconcile_unlocked()

    def reset(self) -> WorkflowState:
        with self._project_lock.locked(self._project):
            state = WorkflowState.initial()
            self._store.write_workflow(self._project, state)
            self._store.delete_handoff(self._project)
            return state

    def next(self, *, source_pane: str | None = None) -> TransferResult:
        with self._project_lock.locked(self._project):
            state = self._reconcile_unlocked()
            snapshot = self._backend.inspect_session(self._session_name)
            self._validate_session(snapshot)
            source = self._resolve_source(snapshot, source_pane)
            if source is not state.current_role:
                raise AtCodeError(
                    "WORKFLOW_ROLE_MISMATCH",
                    f"Expected {state.current_role.value}, got {source.value}.",
                    hint=f"Switch to the {state.current_role.value} role.",
                )

            handoff = self._store.read_handoff(self._project)
            if handoff is not None and handoff.delivery is DeliveryState.PENDING:
                self._validate_pending(handoff, state, source)
                return self._deliver(state, handoff)

            output = self._backend.read_role_output(self._session_name, source)
            parsed = self._parser.parse(output, source)
            if state.last_digests.get(source) == parsed.digest:
                raise AtCodeError(
                    "HANDOFF_ALREADY_DELIVERED",
                    "This role handoff was already delivered.",
                    hint="Produce a new handoff after completing more work.",
                )

            now = self._clock()
            handoff = Handoff(
                transfer_id=state.last_transfer_id + 1,
                from_role=source,
                to_role=_NEXT_ROLE[source],
                decision=parsed.decision,
                delivery=DeliveryState.PENDING,
                digest=parsed.digest,
                body=parsed.body,
                created_at=now,
            )
            self._store.write_handoff(self._project, handoff)
            return self._deliver(state, handoff)

    def _reconcile_unlocked(self) -> WorkflowState:
        state = self._store.read_workflow(self._project)
        reconciled = reconcile_state(
            state,
            self._store.read_handoff(self._project),
            self._clock(),
        )
        if reconciled != state:
            self._store.write_workflow(self._project, reconciled)
        return reconciled

    def _deliver(
        self,
        state: WorkflowState,
        handoff: Handoff,
    ) -> TransferResult:
        self._backend.deliver_text(
            self._session_name,
            handoff.to_role,
            transfer_text(handoff),
        )
        delivered_at = self._clock()
        delivered = replace(
            handoff,
            delivery=DeliveryState.DELIVERED,
            delivered_at=delivered_at,
        )
        self._store.write_handoff(self._project, delivered)
        next_state = transition(
            state,
            delivered.from_role,
            delivered.decision,
            delivered.transfer_id,
            delivered.digest,
            delivered_at,
        )
        self._store.write_workflow(self._project, next_state)

        focus_warning = None
        try:
            self._backend.focus_role(self._session_name, delivered.to_role)
        except AtCodeError as error:
            focus_warning = error.message
        return TransferResult(
            delivered.transfer_id,
            delivered.from_role,
            delivered.to_role,
            next_state.status,
            focus_warning,
        )

    def _validate_pending(
        self,
        handoff: Handoff,
        state: WorkflowState,
        source: Role,
    ) -> None:
        if (
            handoff.from_role is not source
            or handoff.to_role is not _NEXT_ROLE[source]
            or handoff.transfer_id <= state.last_transfer_id
        ):
            raise AtCodeError(
                "HANDOFF_INVALID",
                "Pending handoff does not match the current workflow.",
            )

    @staticmethod
    def _validate_session(snapshot: SessionSnapshot) -> None:
        if not snapshot.exists:
            raise AtCodeError(
                "SESSION_NOT_RUNNING",
                "The project session is not running.",
                hint="Run atcode start first.",
            )
        if (
            snapshot.layout is None
            or len(snapshot.endpoints) != len(Role)
            or {item.role for item in snapshot.endpoints} != set(Role)
        ):
            raise AtCodeError(
                "SESSION_DEGRADED",
                "The project session has invalid role endpoints.",
                hint="Run atcode stop, then atcode start.",
            )

    @staticmethod
    def _resolve_source(
        snapshot: SessionSnapshot,
        source_pane: str | None,
    ) -> Role:
        matches = (
            [item for item in snapshot.endpoints if item.pane == source_pane]
            if source_pane is not None
            else [item for item in snapshot.endpoints if item.active]
        )
        if len(matches) != 1:
            raise AtCodeError(
                "WORKFLOW_ROLE_MISMATCH",
                "Could not identify exactly one source role pane.",
            )
        return matches[0].role


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
