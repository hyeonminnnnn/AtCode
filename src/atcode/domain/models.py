"""Domain value objects shared by application services and ports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Project:
    """A target project registered outside its own root."""

    project_id: str
    name: str
    root: Path
    created_at: str


class Role(str, Enum):
    PM = "pm"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"


class Layout(str, Enum):
    PANES = "panes"
    WINDOWS = "windows"


class HandoffDecision(str, Enum):
    READY = "ready"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeliveryState(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"


class WorkflowStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    REWORK = "rework"
    COMPLETE = "complete"


@dataclass(frozen=True)
class RoleAssignment:
    adapter: str


@dataclass(frozen=True)
class RuntimeConfig:
    backend: str
    roles: Mapping[Role, RoleAssignment]
    layout: Layout = Layout.PANES

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": 1,
            "backend": self.backend,
            "layout": self.layout.value,
            "roles": {
                role.value: {"adapter": self.roles[role].adapter} for role in Role
            },
        }


@dataclass(frozen=True)
class RenderedPrompt:
    text: str
    path: Path


class DiagnosticLevel(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class DiagnosticResult:
    name: str
    level: DiagnosticLevel
    message: str
    hint: str | None = None

    @property
    def ok(self) -> bool:
        return self.level is not DiagnosticLevel.FAIL


@dataclass(frozen=True)
class RoleLaunchContext:
    project: Project
    role: Role
    prompt: RenderedPrompt
    atcode_home: Path


@dataclass(frozen=True)
class LaunchSpec:
    executable: str
    arguments: tuple[str, ...] = ()
    environment: Mapping[str, str] | None = None


@dataclass(frozen=True)
class RoleSpec:
    role: Role
    cwd: Path
    launch: LaunchSpec


@dataclass(frozen=True)
class SessionSpec:
    session_name: str
    project_root: Path
    layout: Layout
    roles: tuple[RoleSpec, ...]


@dataclass(frozen=True)
class RoleEndpoint:
    role: Role
    window: str
    pane: str
    active: bool = False


@dataclass(frozen=True)
class SessionSnapshot:
    session_name: str
    exists: bool
    layout: Layout | None = None
    endpoints: tuple[RoleEndpoint, ...] = ()

    @property
    def active_role(self) -> Role | None:
        return next((item.role for item in self.endpoints if item.active), None)

    @classmethod
    def stopped(cls, session_name: str) -> "SessionSnapshot":
        return cls(session_name=session_name, exists=False)


class Lifecycle(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    DEGRADED = "degraded"
    ERROR = "error"


@dataclass(frozen=True)
class RoleRuntime:
    role: Role
    adapter: str
    endpoint: str


@dataclass(frozen=True)
class ParsedHandoff:
    decision: HandoffDecision
    body: str
    digest: str


@dataclass(frozen=True)
class Handoff:
    transfer_id: int
    from_role: Role
    to_role: Role
    decision: HandoffDecision
    delivery: DeliveryState
    digest: str
    body: str
    created_at: str
    delivered_at: str | None = None


@dataclass(frozen=True)
class WorkflowState:
    status: WorkflowStatus
    current_role: Role
    round: int
    last_transfer_id: int
    last_digests: Mapping[Role, str]
    updated_at: str | None

    @classmethod
    def initial(cls) -> "WorkflowState":
        return cls(WorkflowStatus.IDLE, Role.PM, 0, 0, {}, None)


@dataclass(frozen=True)
class RuntimeState:
    project_id: str
    backend: str
    session_name: str
    status: Lifecycle
    started_at: str | None
    stopped_at: str | None
    roles: tuple[RoleRuntime, ...]
    last_error: str | None = None
    layout: Layout = Layout.PANES
