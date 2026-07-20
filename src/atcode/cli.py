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
    for name in ("init", "attach", "stop", "status", "doctor"):
        command = commands.add_parser(name)
        command.add_argument("--project")
    start = commands.add_parser("start")
    start.add_argument("--project")
    start.add_argument("--fresh", action="store_true")
    next_command = commands.add_parser("next")
    next_command.add_argument("--project")
    next_command.add_argument("--session", help=argparse.SUPPRESS)
    next_command.add_argument("--pane", help=argparse.SUPPRESS)
    next_command.add_argument("--notify", action="store_true", help=argparse.SUPPRESS)
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
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            project = container.projects.init(args.project, cwd)
            print(f"프로젝트 초기화: {project.root}", file=stdout)
        elif args.command == "start":
            project = container.registered_project(args.project, cwd)
            sessions = container.sessions(project)
            if args.fresh:
                _reset_fresh(container, project, stdin, stdout)
            state = sessions.start()
            print(f"{project.name}: {state.status.value}", file=stdout)
            binding = container.backend.install_next_action()
            if binding.level is DiagnosticLevel.WARN:
                print(f"WARNING {binding.name}: {binding.message}", file=stdout)
                if binding.hint:
                    print(f"Hint: {binding.hint}", file=stdout)
        elif args.command in {"attach", "stop", "status"}:
            project = container.registered_project(args.project, cwd)
            sessions = container.sessions(project)
            if args.command == "attach":
                sessions.attach()
            else:
                state = getattr(sessions, args.command)()
                print(f"{project.name}: {state.status.value}", file=stdout)
                if args.command == "status":
                    workflow = container.workflows(project).current()
                    handoff = container.workflow_store.read_handoff(project)
                    delivery = handoff.delivery.value if handoff is not None else "none"
                    print(
                        f"workflow={workflow.status.value} "
                        f"role={workflow.current_role.value} "
                        f"round={workflow.round} "
                        f"transfer={workflow.last_transfer_id} "
                        f"delivery={delivery}",
                        file=stdout,
                    )
        elif args.command == "next":
            if args.session:
                project = container.project_for_session(args.session)
            else:
                if args.pane:
                    raise AtCodeError(
                        "NEXT_SOURCE_INVALID",
                        "--pane requires the internal --session option.",
                        exit_code=2,
                    )
                project = container.registered_project(args.project, cwd)
            result = container.workflows(project).next(source_pane=args.pane)
            message = (
                f"transfer={result.transfer_id} "
                f"{result.from_role.value} -> {result.to_role.value} "
                f"workflow={result.workflow_status.value}"
            )
            if result.focus_warning:
                message += f" focus-warning={result.focus_warning}"
            print(message, file=stdout)
            if args.notify:
                _display_message(container, message)
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
        if args.command == "next" and getattr(args, "notify", False):
            _display_message(container, f"ERROR {error.code}: {error.message}")
        print(f"ERROR {error.code}: {error.message}", file=stderr)
        if error.hint:
            print(f"Hint: {error.hint}", file=stderr)
        return error.exit_code


def _reset_fresh(
    container: AppContainer,
    project,
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    session_name = f"atcode-{project.project_id}"
    if container.backend.inspect_session(session_name).exists:
        raise AtCodeError(
            "FRESH_REQUIRES_STOPPED_SESSION",
            "Stop the project session before using --fresh.",
            hint="Run atcode stop first.",
        )
    workflow_service = container.workflows(project)
    workflow = workflow_service.current()
    handoff = container.workflow_store.read_handoff(project)
    delivery = handoff.delivery.value if handoff is not None else "none"
    print(
        f"현재 workflow={workflow.status.value} "
        f"role={workflow.current_role.value} round={workflow.round} "
        f"transfer={workflow.last_transfer_id} delivery={delivery}",
        file=stdout,
    )
    print("workflow와 최신 handoff를 초기화할까요? [y/N] ", end="", file=stdout)
    if stdin.readline().strip().lower() not in {"y", "yes"}:
        raise AtCodeError("FRESH_CANCELLED", "Fresh start was cancelled.")
    workflow_service.reset()
    print("workflow 초기화 완료", file=stdout)


def _display_message(container: AppContainer, message: str) -> None:
    try:
        container.backend.display_message(message)
    except AtCodeError:
        pass


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
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
