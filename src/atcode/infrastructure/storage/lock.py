"""Cross-platform lock shared by all per-project Runtime state writes."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from atcode.domain.models import Project


class JsonProjectLock:
    def __init__(self, runtime_home: Path) -> None:
        self._home = runtime_home

    @contextmanager
    def locked(self, project: Project) -> Iterator[None]:
        path = self._home / "projects" / project.project_id / "state.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as stream:
            _acquire(stream)
            try:
                yield
            finally:
                _release(stream)


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
