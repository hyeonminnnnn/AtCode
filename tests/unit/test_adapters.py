from __future__ import annotations

from pathlib import Path

import pytest

from atcode.domain.errors import AtCodeError
from atcode.domain.models import (
    DiagnosticLevel,
    Project,
    RenderedPrompt,
    Role,
    RoleLaunchContext,
)
from atcode.infrastructure.adapters.claude import ClaudeAdapter
from atcode.infrastructure.adapters.codex import CodexAdapter
from atcode.infrastructure.adapters.gemini import GeminiAdapter
from atcode.infrastructure.adapters.registry import AdapterRegistry
from atcode.infrastructure.adapters.shell import ShellAdapter


def context(tmp_path: Path) -> RoleLaunchContext:
    project_root = tmp_path / "target"
    project_root.mkdir()
    prompt_path = tmp_path / "runtime" / "prompt.md"
    prompt_path.parent.mkdir()
    prompt_path.write_text("Developer prompt", encoding="utf-8")
    return RoleLaunchContext(
        project=Project(
            "target-1234567890",
            "target",
            project_root,
            "2026-07-15T00:00:00Z",
        ),
        role=Role.DEVELOPER,
        prompt=RenderedPrompt("Developer prompt", prompt_path),
        atcode_home=tmp_path / "runtime",
    )


def registry() -> AdapterRegistry:
    available = lambda name: f"/usr/bin/{name}"
    return AdapterRegistry(
        (
            CodexAdapter(available),
            ClaudeAdapter(available),
            GeminiAdapter(available),
            ShellAdapter({"SHELL": "/bin/zsh"}, available),
        )
    )


@pytest.mark.parametrize("name", ["codex", "claude", "gemini", "shell"])
def test_registry_returns_supported_adapter(name: str) -> None:
    assert registry().get(name).name == name


def test_codex_uses_positional_initial_prompt(tmp_path: Path) -> None:
    spec = registry().get("codex").build_launch(context(tmp_path))

    assert spec.executable == "codex"
    assert spec.arguments == ("Developer prompt",)


def test_claude_uses_positional_initial_prompt(tmp_path: Path) -> None:
    spec = registry().get("claude").build_launch(context(tmp_path))

    assert spec.executable == "claude"
    assert spec.arguments == ("Developer prompt",)


def test_gemini_uses_interactive_prompt_flag(tmp_path: Path) -> None:
    spec = registry().get("gemini").build_launch(context(tmp_path))

    assert spec.executable == "gemini"
    assert spec.arguments == ("-i", "Developer prompt")


def test_shell_exposes_context_without_executing_prompt(tmp_path: Path) -> None:
    spec = registry().get("shell").build_launch(context(tmp_path))

    assert spec.executable == "/bin/zsh"
    assert spec.arguments == ("-l",)
    assert spec.environment["ATCODE_ROLE"] == "developer"
    assert spec.environment["ATCODE_PROMPT_FILE"].endswith("prompt.md")
    assert "Developer prompt" not in spec.arguments


def test_probe_fails_when_executable_is_missing() -> None:
    adapter = CodexAdapter(lambda _name: None)

    assert adapter.probe().level is DiagnosticLevel.FAIL


def test_registry_rejects_unknown_adapter() -> None:
    with pytest.raises(AtCodeError, match="ADAPTER_UNKNOWN"):
        registry().get("other")
