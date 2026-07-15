"""Project session lifecycle orchestration."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    Lifecycle,
    Project,
    Role,
    RoleLaunchContext,
    RoleRuntime,
    RuntimeConfig,
    RuntimeState,
    SessionSnapshot,
    SessionSpec,
    WindowSpec,
)
from atcode.ports.backend import TerminalBackend
from atcode.ports.storage import StateStore


class SessionService:
    def __init__(
        self,
        *,
        project: Project,
        configuration: Any,
        prompts: Any,
        adapters: Any,
        backend: TerminalBackend,
        state_store: StateStore,
        atcode_home: Path,
    ) -> None:
        self._project = project
        self._configuration = configuration
        self._prompts = prompts
        self._adapters = adapters
        self._backend = backend
        self._state_store = state_store
        self._atcode_home = atcode_home
        self._session_name = f"atcode-{project.project_id}"

    def start(self) -> RuntimeState:
        with self._state_store.locked(self._project):
            config = self._configuration.effective(self._project)
            snapshot = self._backend.inspect_session(self._session_name)
            if snapshot.exists:
                state = self._state_from_snapshot(snapshot, config)
                self._state_store.write(self._project, state)
                if state.status is Lifecycle.DEGRADED:
                    raise AtCodeError(
                        "SESSION_DEGRADED",
                        "The existing project session is missing role windows.",
                        hint="Run atcode stop, then atcode start.",
                    )
                return state

            backend_probe = self._backend.probe()
            if not backend_probe.ok:
                raise AtCodeError(
                    "BACKEND_UNAVAILABLE",
                    backend_probe.message,
                    hint=backend_probe.hint,
                )

            windows: list[WindowSpec] = []
            for role in Role:
                rendered = self._prompts.render(self._project, role)
                assignment = config.roles[role]
                adapter = self._adapters.get(assignment.adapter)
                diagnostic = adapter.probe()
                if not diagnostic.ok:
                    raise AtCodeError(
                        "ADAPTER_NOT_FOUND",
                        f"{role.value}: {diagnostic.message}",
                        hint=diagnostic.hint,
                    )
                context = RoleLaunchContext(
                    self._project,
                    role,
                    rendered,
                    self._atcode_home,
                )
                windows.append(
                    WindowSpec(role.value, self._project.root, adapter.build_launch(context))
                )

            self._backend.create_session(
                SessionSpec(self._session_name, self._project.root, tuple(windows))
            )
            state = self._state_from_snapshot(
                self._backend.inspect_session(self._session_name),
                config,
                starting=True,
            )
            self._state_store.write(self._project, state)
            return state

    def attach(self) -> None:
        snapshot = self._backend.inspect_session(self._session_name)
        if not snapshot.exists:
            raise AtCodeError(
                "SESSION_NOT_RUNNING",
                "The project session is not running.",
                hint="Run atcode start first.",
            )
        self._backend.attach_session(self._session_name)

    def stop(self) -> RuntimeState:
        with self._state_store.locked(self._project):
            config = self._configuration.effective(self._project)
            snapshot = self._backend.inspect_session(self._session_name)
            if snapshot.exists:
                self._backend.terminate_session(self._session_name)
            state = self._state_from_snapshot(
                self._backend.inspect_session(self._session_name),
                config,
                stopping=True,
            )
            self._state_store.write(self._project, state)
            return state

    def status(self) -> RuntimeState:
        with self._state_store.locked(self._project):
            config = self._configuration.effective(self._project)
            state = self._state_from_snapshot(
                self._backend.inspect_session(self._session_name),
                config,
            )
            self._state_store.write(self._project, state)
            return state

    def _state_from_snapshot(
        self,
        snapshot: SessionSnapshot,
        config: RuntimeConfig,
        *,
        starting: bool = False,
        stopping: bool = False,
    ) -> RuntimeState:
        previous = self._state_store.read(self._project)
        now = datetime.now(timezone.utc).isoformat()
        expected = {role.value for role in Role}
        actual = set(snapshot.windows)
        if not snapshot.exists:
            lifecycle = Lifecycle.STOPPED
        elif expected.issubset(actual):
            lifecycle = Lifecycle.RUNNING
        else:
            lifecycle = Lifecycle.DEGRADED
        return RuntimeState(
            project_id=self._project.project_id,
            backend=config.backend,
            session_name=self._session_name,
            status=lifecycle,
            started_at=now if starting else (previous.started_at if previous else None),
            stopped_at=(
                (previous.stopped_at if previous and previous.stopped_at else now)
                if stopping
                else (
                    previous.stopped_at
                    if lifecycle is Lifecycle.STOPPED and previous
                    else None
                )
            ),
            roles=tuple(
                RoleRuntime(role, config.roles[role].adapter, role.value) for role in Role
            ),
        )
