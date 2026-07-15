"""Small helpers shared by built-in CLI Adapters."""

from __future__ import annotations

from collections.abc import Callable

from atcode.domain.models import (
    DiagnosticLevel,
    DiagnosticResult,
    RoleLaunchContext,
)

ExecutableFinder = Callable[[str], str | None]


def probe_executable(
    adapter_name: str,
    executable: str,
    finder: ExecutableFinder,
) -> DiagnosticResult:
    path = finder(executable)
    if path is None:
        return DiagnosticResult(
            adapter_name,
            DiagnosticLevel.FAIL,
            f"Executable not found: {executable}",
            hint=f"Install {adapter_name} or change the role Adapter.",
        )
    return DiagnosticResult(
        adapter_name,
        DiagnosticLevel.PASS,
        f"Executable: {path}",
    )


def launch_environment(context: RoleLaunchContext) -> dict[str, str]:
    return {
        "ATCODE_ROLE": context.role.value,
        "ATCODE_PROJECT_ID": context.project.project_id,
        "ATCODE_PROJECT_ROOT": str(context.project.root),
        "ATCODE_PROMPT_FILE": str(context.prompt.path),
        "ATCODE_HOME": str(context.atcode_home),
    }
