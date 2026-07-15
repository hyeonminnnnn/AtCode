"""AtCode command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import TextIO

from atcode.bootstrap import AppContainer, build_container
from atcode.domain.errors import AtCodeError
from atcode.domain.models import DiagnosticLevel


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="atcode", description="AI Team Runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "start", "attach", "stop", "status", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--project")
    commands.add_parser("list")
    config = commands.add_parser("config")
    actions = config.add_subparsers(dest="config_action", required=True)
    for name in ("show", "get", "set", "unset"):
        action = actions.add_parser(name)
        if name in {"get", "set", "unset"}:
            action.add_argument("key")
        if name == "set":
            action.add_argument("value")
        action.add_argument("--global", dest="global_scope", action="store_true")
        action.add_argument("--project")
    return parser


def run(
    argv: list[str],
    *,
    container: AppContainer,
    cwd: Path,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            project = container.projects.init(args.project, cwd)
            print(f"프로젝트 초기화: {project.root}", file=stdout)
        elif args.command in {"start", "attach", "stop", "status"}:
            project = container.registered_project(args.project, cwd)
            sessions = container.sessions(project)
            if args.command == "attach":
                sessions.attach()
            else:
                state = getattr(sessions, args.command)()
                print(f"{project.name}: {state.status.value}", file=stdout)
        elif args.command == "doctor":
            project = _optional_project(container, args.project, cwd)
            results = container.diagnostics.run(project)
            for result in results:
                print(f"{result.level.value:<4}  {result.name}: {result.message}", file=stdout)
                if result.hint:
                    print(f"      Hint: {result.hint}", file=stdout)
            return 1 if any(result.level is DiagnosticLevel.FAIL for result in results) else 0
        elif args.command == "list":
            for project in container.project_store.list():
                state = container.sessions(project).status()
                print(f"{project.project_id}\t{state.status.value}\t{project.root}", file=stdout)
        elif args.command == "config":
            project = None
            if not args.global_scope:
                project = container.registered_project(args.project, cwd)
            if args.config_action == "show":
                value = container.configuration.effective(project).to_dict()
                print(json.dumps(value, ensure_ascii=False, indent=2), file=stdout)
            elif args.config_action == "get":
                print(container.configuration.get(project, args.key), file=stdout)
            elif args.config_action == "set":
                container.configuration.set(
                    project,
                    args.key,
                    args.value,
                    global_scope=args.global_scope,
                )
            elif args.config_action == "unset":
                container.configuration.unset(
                    project,
                    args.key,
                    global_scope=args.global_scope,
                )
        return 0
    except AtCodeError as error:
        print(f"ERROR {error.code}: {error.message}", file=stderr)
        if error.hint:
            print(f"Hint: {error.hint}", file=stderr)
        return error.exit_code


def _optional_project(
    container: AppContainer,
    explicit: str | None,
    cwd: Path,
):
    try:
        return container.registered_project(explicit, cwd)
    except AtCodeError as error:
        if error.code == "PROJECT_NOT_INITIALIZED" and explicit is None:
            return None
        raise


def main(argv: list[str] | None = None) -> int:
    install_root = Path(__file__).resolve().parents[2]
    container = build_container(env=os.environ, install_root=install_root)
    return run(
        list(sys.argv[1:] if argv is None else argv),
        container=container,
        cwd=Path.cwd(),
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
