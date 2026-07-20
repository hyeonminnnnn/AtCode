"""Extraction and validation of structured role handoff blocks."""

from __future__ import annotations

import hashlib
import re

from atcode.domain.errors import AtCodeError
from atcode.domain.models import HandoffDecision, ParsedHandoff, Role

MAX_HANDOFF_BYTES = 32 * 1024
_BLOCK = re.compile(
    r"<ATCODE_HANDOFF>\s*(.*?)\s*</ATCODE_HANDOFF>",
    re.DOTALL,
)
_ALLOWED = {
    Role.PM: frozenset({HandoffDecision.READY}),
    Role.DEVELOPER: frozenset({HandoffDecision.READY}),
    Role.REVIEWER: frozenset(
        {HandoffDecision.APPROVED, HandoffDecision.REJECTED}
    ),
}


class HandoffParser:
    def parse(self, output: str, role: Role) -> ParsedHandoff:
        blocks = _BLOCK.findall(output)
        if not blocks:
            raise AtCodeError(
                "HANDOFF_MISSING",
                "A complete ATCODE_HANDOFF block was not found.",
            )

        lines = blocks[-1].strip().splitlines()
        if not lines or not lines[0].startswith("STATUS: "):
            raise AtCodeError(
                "HANDOFF_STATUS_INVALID",
                "Handoff STATUS is missing.",
            )
        try:
            decision = HandoffDecision(
                lines[0].removeprefix("STATUS: ").strip()
            )
        except ValueError as error:
            raise AtCodeError(
                "HANDOFF_STATUS_INVALID",
                "Handoff STATUS is unsupported.",
            ) from error
        if decision not in _ALLOWED[role]:
            raise AtCodeError(
                "HANDOFF_STATUS_INVALID",
                f"{role.value} cannot send STATUS {decision.value}.",
            )

        body = "\n".join(lines[1:]).strip()
        if not body:
            raise AtCodeError("HANDOFF_BODY_INVALID", "Handoff body is empty.")
        if len(body.encode("utf-8")) > MAX_HANDOFF_BYTES:
            raise AtCodeError("HANDOFF_TOO_LARGE", "Handoff exceeds 32 KiB.")

        digest_input = f"{role.value}\0{decision.value}\0{body}".encode("utf-8")
        digest = f"sha256:{hashlib.sha256(digest_input).hexdigest()}"
        return ParsedHandoff(decision, body, digest)
