"""Runtime path resolution and application composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """All writable paths owned by the AtCode Runtime."""

    home: Path
    projects: Path
    global_config: Path


def resolve_runtime_paths(
    env: Mapping[str, str],
    install_root: Path,
) -> RuntimePaths:
    """Resolve Runtime paths without creating files or directories."""

    configured_home = env.get("ATCODE_HOME")
    if configured_home:
        home_candidate = Path(configured_home).expanduser()
        if not home_candidate.is_absolute():
            raise ValueError("ATCODE_HOME must be an absolute path")
        home = home_candidate.resolve()
    else:
        home = (install_root / "data").resolve()

    return RuntimePaths(
        home=home,
        projects=home / "projects",
        global_config=home / "config.json",
    )
