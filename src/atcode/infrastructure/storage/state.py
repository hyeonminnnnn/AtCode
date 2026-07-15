"""Atomic JSON Runtime state with a per-project file lock."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    Lifecycle,
    Project,
    Role,
    RoleRuntime,
    RuntimeState,
)
from atcode.infrastructure.storage.json_file import read_json, write_json_atomic

_LEGACY_ROLES = frozenset({"tester", "docs"})


class JsonStateStore:
    def __init__(self, runtime_home: Path) -> None:
        self._home = runtime_home

    def read(self, project: Project) -> RuntimeState | None:
        path = self._state_path(project)
        if not path.is_file():
            return None
        try:
            value = read_json(path)
            if value.get("schemaVersion") != 1:
                raise ValueError("unsupported schemaVersion")
            if value.get("projectId") != project.project_id:
                raise ValueError("state projectId does not match its directory")
            roles: list[RoleRuntime] = []
            for item in value["roles"]:
                role_name = item["role"]
                adapter = item["adapter"]
                window = item["window"]
                if role_name in _LEGACY_ROLES:
                    continue
                roles.append(RoleRuntime(Role(role_name), adapter, window))
            return RuntimeState(
                project_id=value["projectId"],
                backend=value["backend"],
                session_name=value["backendSession"],
                status=Lifecycle(value["status"]),
                started_at=value.get("startedAt"),
                stopped_at=value.get("stoppedAt"),
                roles=tuple(roles),
                last_error=value.get("lastError"),
            )
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "STATE_INVALID",
                f"Runtime state is invalid: {path}",
                hint="Run atcode status after repairing or removing this state file.",
            ) from error

    def write(self, project: Project, state: RuntimeState) -> None:
        write_json_atomic(
            self._state_path(project),
            {
                "schemaVersion": 1,
                "projectId": state.project_id,
                "backend": state.backend,
                "backendSession": state.session_name,
                "status": state.status.value,
                "startedAt": state.started_at,
                "stoppedAt": state.stopped_at,
                "roles": [
                    {
                        "role": item.role.value,
                        "adapter": item.adapter,
                        "window": item.window,
                    }
                    for item in state.roles
                ],
                "lastError": state.last_error,
            },
        )

    @contextmanager
    def locked(self, project: Project) -> Iterator[None]:
        path = self._project_dir(project) / "state.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            _acquire(stream)
            try:
                yield
            finally:
                _release(stream)

    def _project_dir(self, project: Project) -> Path:
        return self._home / "projects" / project.project_id

    def _state_path(self, project: Project) -> Path:
        return self._project_dir(project) / "state.json"


def _acquire(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _release(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
