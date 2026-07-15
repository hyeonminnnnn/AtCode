"""Runtime path resolution and application composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path

from atcode.application.configuration import ConfigurationService
from atcode.application.diagnostics import DiagnosticsService
from atcode.application.projects import ProjectService
from atcode.application.prompts import PromptRenderer
from atcode.application.sessions import SessionService
from atcode.domain.errors import AtCodeError
from atcode.domain.models import Project
from atcode.infrastructure.adapters.claude import ClaudeAdapter
from atcode.infrastructure.adapters.codex import CodexAdapter
from atcode.infrastructure.adapters.gemini import GeminiAdapter
from atcode.infrastructure.adapters.registry import AdapterRegistry
from atcode.infrastructure.adapters.shell import ShellAdapter
from atcode.infrastructure.process import SubprocessRunner
from atcode.infrastructure.storage.configuration import JsonConfigurationStore
from atcode.infrastructure.storage.projects import JsonProjectStore
from atcode.infrastructure.storage.prompts import FilesystemPromptStore
from atcode.infrastructure.storage.state import JsonStateStore
from atcode.infrastructure.tmux_backend import TmuxBackend
from atcode.ports.backend import TerminalBackend


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


@dataclass(frozen=True)
class AppContainer:
    paths: RuntimePaths
    project_store: JsonProjectStore
    projects: ProjectService
    configuration: ConfigurationService
    prompts: PromptRenderer
    adapters: AdapterRegistry
    backend: TerminalBackend
    state_store: JsonStateStore
    diagnostics: DiagnosticsService

    def registered_project(self, explicit: str | Path | None, cwd: Path) -> Project:
        root = self.projects.resolve_root(explicit, cwd)
        project = self.project_store.find_by_root(root)
        if project is None:
            raise AtCodeError(
                "PROJECT_NOT_INITIALIZED",
                f"Project is not initialized: {root}",
                hint="Run atcode init in the project root.",
            )
        return project

    def sessions(self, project: Project) -> SessionService:
        return SessionService(
            project=project,
            configuration=self.configuration,
            prompts=self.prompts,
            adapters=self.adapters,
            backend=self.backend,
            state_store=self.state_store,
            atcode_home=self.paths.home,
        )


def build_container(
    *,
    env: Mapping[str, str] = os.environ,
    install_root: Path,
    backend: TerminalBackend | None = None,
    adapters: AdapterRegistry | None = None,
) -> AppContainer:
    paths = resolve_runtime_paths(env, install_root)
    runner = SubprocessRunner()
    project_store = JsonProjectStore(paths.projects)
    adapter_registry = adapters or AdapterRegistry(
        (
            CodexAdapter(),
            ClaudeAdapter(),
            GeminiAdapter(),
            ShellAdapter(env),
        )
    )
    terminal_backend = backend or TmuxBackend(runner, env)
    configuration_store = JsonConfigurationStore(paths.home)
    configuration = ConfigurationService(
        configuration_store,
        allowed_backends={"tmux"},
        allowed_adapters=set(adapter_registry.names),
    )

    def git_root_finder(cwd: Path) -> Path | None:
        try:
            result = runner.run(
                ("git", "-C", str(cwd), "rev-parse", "--show-toplevel")
            )
        except AtCodeError:
            return None
        return Path(result.stdout.strip()) if result.returncode == 0 else None

    projects = ProjectService(project_store, git_root_finder)
    prompts = PromptRenderer(
        FilesystemPromptStore(install_root / "prompts", paths.home),
        paths.home,
    )
    state_store = JsonStateStore(paths.home)
    diagnostics = DiagnosticsService(
        paths=paths,
        configuration=configuration,
        adapters=adapter_registry,
        backend=terminal_backend,
    )
    return AppContainer(
        paths,
        project_store,
        projects,
        configuration,
        prompts,
        adapter_registry,
        terminal_backend,
        state_store,
        diagnostics,
    )
