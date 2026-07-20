from __future__ import annotations

import pytest

from atcode.application.handoffs import HandoffParser, MAX_HANDOFF_BYTES
from atcode.domain.errors import AtCodeError
from atcode.domain.models import HandoffDecision, Role


def test_parser_returns_latest_complete_handoff() -> None:
    output = """
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
old
</ATCODE_HANDOFF>
progress
<ATCODE_HANDOFF>
STATUS: ready
SUMMARY:
new
</ATCODE_HANDOFF>
"""

    parsed = HandoffParser().parse(output, Role.PM)

    assert parsed.decision is HandoffDecision.READY
    assert parsed.body == "SUMMARY:\nnew"
    assert parsed.digest.startswith("sha256:")


@pytest.mark.parametrize(
    ("role", "status"),
    [
        (Role.PM, "approved"),
        (Role.DEVELOPER, "rejected"),
        (Role.REVIEWER, "ready"),
    ],
)
def test_parser_rejects_status_not_allowed_for_role(role: Role, status: str) -> None:
    output = (
        "<ATCODE_HANDOFF>\n"
        f"STATUS: {status}\n"
        "SUMMARY:\nbody\n"
        "</ATCODE_HANDOFF>"
    )

    with pytest.raises(AtCodeError, match="HANDOFF_STATUS_INVALID"):
        HandoffParser().parse(output, role)


def test_parser_rejects_missing_complete_block() -> None:
    with pytest.raises(AtCodeError, match="HANDOFF_MISSING"):
        HandoffParser().parse("<ATCODE_HANDOFF>\nSTATUS: ready", Role.PM)


def test_parser_rejects_empty_body() -> None:
    output = "<ATCODE_HANDOFF>\nSTATUS: ready\n</ATCODE_HANDOFF>"

    with pytest.raises(AtCodeError, match="HANDOFF_BODY_INVALID"):
        HandoffParser().parse(output, Role.PM)


def test_parser_rejects_body_over_limit() -> None:
    output = (
        "<ATCODE_HANDOFF>\nSTATUS: ready\n"
        + ("가" * (MAX_HANDOFF_BYTES + 1))
        + "\n</ATCODE_HANDOFF>"
    )

    with pytest.raises(AtCodeError, match="HANDOFF_TOO_LARGE"):
        HandoffParser().parse(output, Role.PM)
