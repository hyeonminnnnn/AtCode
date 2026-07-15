"""Domain value objects shared by application services and ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Project:
    """A target project registered outside its own root."""

    project_id: str
    name: str
    root: Path
    created_at: str
