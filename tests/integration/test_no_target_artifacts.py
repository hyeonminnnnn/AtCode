from __future__ import annotations

from pathlib import Path

from atcode.domain.models import Role
from test_cli import invoke, make_container


def snapshot(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*")}


def test_full_lifecycle_leaves_target_tree_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("print('target')\n", encoding="utf-8")
    before = snapshot(target)
    container = make_container(tmp_path)

    assert invoke(container, target, "init")[0] == 0
    assert invoke(container, target, "start")[0] == 0
    assert invoke(container, target, "status")[0] == 0
    assert invoke(container, target, "stop")[0] == 0

    assert snapshot(target) == before
    assert source.read_text(encoding="utf-8") == "print('target')\n"


def test_full_relay_cycle_leaves_target_tree_unchanged(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("print('target')\n", encoding="utf-8")
    before = snapshot(target)
    container = make_container(tmp_path)
    invoke(container, target, "init")
    invoke(container, target, "start")

    handoffs = {
        Role.PM: "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nplan\n</ATCODE_HANDOFF>",
        Role.DEVELOPER: (
            "<ATCODE_HANDOFF>\nSTATUS: ready\nSUMMARY:\nimplemented\n"
            "</ATCODE_HANDOFF>"
        ),
        Role.REVIEWER: (
            "<ATCODE_HANDOFF>\nSTATUS: approved\nSUMMARY:\nverified\n"
            "</ATCODE_HANDOFF>"
        ),
    }
    for role in Role:
        container.backend.outputs[role] = handoffs[role]
        assert invoke(container, target, "next")[0] == 0
        assert snapshot(target) == before

    assert source.read_text(encoding="utf-8") == "print('target')\n"
