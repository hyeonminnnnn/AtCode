# AtCode Phase 1 Design

> 역할 모델 변경: 이 문서의 5역할 관련 내용은
> `2026-07-15-three-role-runtime-design.md`로 대체되었다. 현재 Phase 1의 고정
> 역할은 PM, Developer, Reviewer 세 개다.

## 1. Objective

AtCode is an AI Team Runtime that runs multiple AI CLIs as a reusable development team. It manages the fixed Phase 1 roles PM, Developer, Reviewer, Tester, and Docs while remaining independent of any particular AI CLI or terminal backend.

Phase 1 targets Python 3.11 or newer on WSL2 and native Linux. It uses tmux as the first terminal backend and supports Codex, Claude, Gemini, and Shell adapters.

The primary invariant is that AtCode management artifacts never appear in the target project. Runtime configuration, state, rendered prompts, and future coordination data live under `ATCODE_HOME`. During development, the default is `<AtCode repository>/data`.

AtCode itself does not create metadata, workspaces, logs, or ignore rules in the target project. AI CLIs launched by AtCode may modify the target project's source files when the user asks them to perform development work.

## 2. Assumptions

1. AtCode runs inside WSL2 or native Linux, not directly in Windows PowerShell or Command Prompt.
2. Windows-hosted projects are accessed through WSL paths such as `/mnt/d/project/SmileLRS`.
3. Git improves project-root detection but is not required.
4. A project must be registered with `atcode init` before its team can be started.
5. Phase 1 uses one tmux session per registered project.
6. Phase 1 roles are fixed to `pm`, `developer`, `reviewer`, `tester`, and `docs`.
7. Role-to-adapter assignments and role prompts are configurable.
8. AtCode supplies each AI CLI with its initial role prompt at launch. Later interaction is manual.
9. Agent Relay, `next`, Task Queue, and automatic Workflow belong to Phase 2.
10. Installation and removal are scripts, not `atcode` subcommands.

## 3. Scope

### 3.1 Included

- Project-root detection and registration
- Git and non-Git projects
- Project-specific Runtime workspaces under `ATCODE_HOME`
- Global configuration with project-specific overrides
- One tmux session per project
- One tmux window per fixed role
- Role-specific Adapter launch
- Role-prompt rendering and initial delivery
- Runtime state persistence and reconciliation
- Environment diagnostics
- Development install and uninstall scripts
- Unit, contract, integration, and no-target-artifact tests

### 3.2 Excluded

- Agent-to-Agent messaging
- `atcode next`
- `send-keys` or equivalent terminal-input injection
- `capture-pane` or AI-output collection
- Task Queue
- Automatic Agent Relay or Workflow
- User-defined roles
- Web UI
- Database
- Native Windows execution
- Target-project configuration or Runtime workspace
- Persistent Agent logs
- Dynamic Python plugin discovery

## 4. Public Commands

```text
atcode init [--project PATH]
atcode start [--project PATH]
atcode attach [--project PATH]
atcode stop [--project PATH]
atcode status [--project PATH]
atcode doctor [--project PATH]
atcode config show [--global] [--project PATH]
atcode config get KEY [--global] [--project PATH]
atcode config set KEY VALUE [--global] [--project PATH]
atcode config unset KEY [--global] [--project PATH]
atcode list
```

Development installation uses:

```text
scripts/install.sh
scripts/uninstall.sh
```

`scripts/uninstall.sh` removes only the installed command by default. It preserves `ATCODE_HOME`. The explicit `scripts/uninstall.sh --purge-data` option may remove the resolved Runtime data directory after displaying the exact target path and receiving interactive confirmation.

## 5. Architecture

AtCode uses a layered modular monolith.

```text
CLI
  -> Application Services
      -> Domain Models
      -> Ports
          <- Terminal Backend implementation
          <- Agent Adapter implementations
          <- File Store implementations
```

Dependency rules:

- CLI depends on Application services.
- Application depends on Domain models and Ports.
- Infrastructure implements Ports.
- Domain code does not import Infrastructure or CLI code.
- Application code does not know tmux commands or AI CLI flags.
- `ATCODE_HOME` is resolved once at the composition root and injected through Runtime paths.

No event bus, dependency-injection framework, async framework, database abstraction, or dynamic plugin loader is introduced in Phase 1.

## 6. Source Layout

```text
AtCode/
├── bin/
│   └── atcode
├── src/
│   └── atcode/
│       ├── __init__.py
│       ├── __main__.py
│       ├── bootstrap.py
│       ├── cli.py
│       ├── domain/
│       │   ├── models.py
│       │   └── errors.py
│       ├── application/
│       │   ├── projects.py
│       │   ├── sessions.py
│       │   ├── configuration.py
│       │   └── diagnostics.py
│       ├── ports/
│       │   ├── backend.py
│       │   ├── adapter.py
│       │   └── storage.py
│       └── infrastructure/
│           ├── process.py
│           ├── tmux_backend.py
│           ├── adapters/
│           │   ├── registry.py
│           │   ├── codex.py
│           │   ├── claude.py
│           │   ├── gemini.py
│           │   └── shell.py
│           └── storage/
│               ├── projects.py
│               ├── configuration.py
│               └── state.py
├── prompts/
│   ├── pm.md
│   ├── developer.md
│   ├── reviewer.md
│   ├── tester.md
│   └── docs.md
├── scripts/
│   ├── install.sh
│   └── uninstall.sh
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── data/
├── pyproject.toml
├── README.md
└── .gitignore
```

`bin/atcode` is a thin launcher. Business logic belongs under `src/atcode`.

The AtCode repository's own `.gitignore` may exclude its virtual environment, caches, and generated `data` contents. AtCode never modifies the target project's `.gitignore`.

## 7. Runtime Paths and Project Resolution

Storage modules receive a resolved `RuntimePaths` value. They do not construct paths from a hard-coded `data` directory.

Resolution of `ATCODE_HOME`:

1. Use the absolute path from the `ATCODE_HOME` environment variable when present.
2. Otherwise use `<AtCode installation root>/data`.
3. Reject an invalid or non-directory parent path with a structured error.

Project-root resolution order:

1. Explicit `--project PATH`
2. The longest registered project root containing the current directory
3. `git rev-parse --show-toplevel`, when available and successful
4. The current directory

The selected root is canonicalized with `Path.resolve()` and must exist as a directory.

Project IDs combine a readable slug and a deterministic path hash:

```text
smilelrs-a13f82c941
```

A moved project is treated as a different registration. `doctor` reports registered roots that no longer exist.

## 8. Runtime Workspace

```text
ATCODE_HOME/
├── config.json
└── projects/
    └── <project-id>/
        ├── project.json
        ├── config.json
        ├── state.json
        ├── state.lock
        └── workspace/
            └── prompts/
                ├── pm.md
                ├── developer.md
                ├── reviewer.md
                ├── tester.md
                └── docs.md
```

Phase 1 does not pre-create empty `tasks`, `handoffs`, `messages`, or `logs` directories.

The project store discovers registrations by scanning `ATCODE_HOME/projects/*/project.json`. A separate global index is not required for the expected Phase 1 scale.

## 9. Configuration

JSON is used for configuration and state so the Runtime has no TOML-writing dependency. All files contain `schemaVersion`.

Effective configuration is merged in this order:

```text
built-in defaults <- global config <- project override
```

Default configuration:

```json
{
  "schemaVersion": 1,
  "backend": "tmux",
  "roles": {
    "pm": {"adapter": "claude"},
    "developer": {"adapter": "codex"},
    "reviewer": {"adapter": "gemini"},
    "tester": {"adapter": "codex"},
    "docs": {"adapter": "claude"}
  }
}
```

Project configuration stores only overrides. `atcode config show` displays the effective configuration. Mutating commands target the current project unless `--global` is supplied.

Unknown keys, unknown adapters, invalid role names, and incompatible value types fail validation before a file is modified.

## 10. Domain Model

Phase 1 uses small immutable value objects where practical:

- `Project`: ID, display name, canonical root, registration timestamp
- `Role`: one of the five fixed role identifiers
- `RoleAssignment`: role and Adapter name
- `RuntimeConfig`: Backend and role assignments
- `RoleLaunchContext`: project, role, rendered prompt text and path
- `LaunchSpec`: executable, arguments, and non-secret environment
- `WindowSpec`: role window name, working directory, and launch specification
- `SessionSpec`: Backend session name, project root, and windows
- `SessionSnapshot`: actual Backend-observed session and windows
- `RuntimeState`: last observed lifecycle and timestamps
- `DiagnosticResult`: check name, PASS/WARN/FAIL, and actionable hint

## 11. Terminal Backend Contract

```python
class TerminalBackend(Protocol):
    def probe(self) -> DiagnosticResult: ...
    def session_exists(self, session_name: str) -> bool: ...
    def create_session(self, spec: SessionSpec) -> None: ...
    def inspect_session(self, session_name: str) -> SessionSnapshot: ...
    def attach_session(self, session_name: str) -> None: ...
    def terminate_session(self, session_name: str) -> None: ...
```

The Phase 1 contract intentionally omits input delivery and output capture.

`TmuxBackend.create_session`:

1. Confirms that the session does not already exist.
2. Creates a detached session with the PM window.
3. Creates the remaining role windows.
4. Selects the PM window.
5. Verifies the actual window set.
6. Removes only the newly created session if partial creation fails.

`attach_session` uses `attach-session` outside tmux and `switch-client` inside tmux.

External commands run through argument arrays with `shell=False`. At the tmux shell-command boundary, `LaunchSpec` is serialized exactly once with `shlex.join()`.

Backend-observed lifecycle values are:

- `stopped`: no session
- `running`: session and every required role window exist
- `degraded`: session exists but required windows are missing
- `error`: inspection failed

## 12. Agent Adapter Contract

```python
class AgentAdapter(Protocol):
    @property
    def name(self) -> str: ...

    def probe(self) -> DiagnosticResult: ...
    def build_launch(self, context: RoleLaunchContext) -> LaunchSpec: ...
```

Phase 1 has an explicit Registry:

```text
codex  -> CodexAdapter
claude -> ClaudeAdapter
gemini -> GeminiAdapter
shell  -> ShellAdapter
```

An Adapter knows its CLI's executable and launch flags. It does not know tmux, session names, state files, or project registration.

Exact Codex, Claude, and Gemini options must be verified against the installed CLI's `--help` and official documentation during implementation. AtCode does not guess unsupported flags and does not add permission-bypass options by default.

`ShellAdapter` launches a login shell and exposes only non-secret context such as role, project root, and prompt-file path through environment variables.

## 13. Prompt Management

Source templates live under `prompts/`. `atcode start` renders them into the project's Runtime workspace using a fixed token set:

```text
{{PROJECT_NAME}}
{{PROJECT_ROOT}}
{{PROJECT_ID}}
{{ROLE}}
{{ATCODE_HOME}}
```

No general-purpose template engine is used.

All role prompts state:

- The role and its responsibilities
- The canonical target-project root
- AtCode management artifacts must not be created in the target project
- Runtime artifacts belong under `ATCODE_HOME`
- User-requested source changes in the target project are allowed
- Agent-to-Agent messaging is not available in Phase 1

The initial role prompt is delivered once at CLI launch. The user's actual task is entered manually after launch and is not persisted by the Phase 1 Runtime.

## 14. State Management

`state.json` is a cache of the last observation, not the source of truth. Backend inspection determines the actual current status.

State includes:

- Schema version
- Project ID
- Backend and Backend session name
- Last observed lifecycle
- Start and stop timestamps
- Role, Adapter, and window assignments
- A sanitized last error code, when applicable

State does not include prompts, AI output, user tasks, secrets, or full external commands.

Writes use a sibling temporary file followed by `os.replace()`. A per-project file lock prevents concurrent lifecycle mutations. `status` reconciles stale stored state with Backend observations.

## 15. Application Behavior

### `init`

- Resolve and validate the project root.
- Create only the corresponding Runtime directory under `ATCODE_HOME`.
- Preserve existing project configuration on repeated execution.
- Never write to the target project.

### `start`

- Require an initialized project.
- Load and validate effective configuration.
- Render all prompts.
- Probe the Backend and every assigned Adapter.
- Build all launch specifications before creating a session.
- Create no partial session when preflight validation fails.
- Treat an already-running valid session as an idempotent success with an attach hint.

### `attach`

- Attach or switch to the project session.
- Show a start hint when no session exists.

### `stop`

- Terminate only the selected project's session.
- Treat an already-stopped project as success.
- Reconcile persisted state.

### `status`

- Inspect the actual Backend.
- Display role windows and Adapter assignments.
- Reconcile persisted state.

### `list`

- List registered project ID, root, and actual status.

### `doctor`

- Report PASS, WARN, or FAIL without mutating the environment.
- Check platform, Python, `ATCODE_HOME`, tmux, assigned CLIs, prompts, project registration, JSON schemas, and state/session consistency.
- Return nonzero only when one or more required checks fail.

## 16. Error Semantics

Application and Domain code raise structured AtCode errors. CLI translates them into concise messages and stable process exit classes.

```text
0  success
1  Runtime or environment failure
2  command usage or configuration validation failure
```

Errors include a machine-readable code, a short explanation, and an actionable hint. They do not expose prompt content, secrets, or unnecessary stack traces during normal CLI use.

## 17. Security and Safety

- Never read or modify target-project `.env` files.
- Never use `shell=True` for process execution.
- Validate Adapter and Backend names against their Registries.
- Derive tmux identifiers from sanitized Runtime-owned values.
- Canonicalize target paths before registration.
- Write only below the resolved `ATCODE_HOME`.
- Do not pass CLI permission-bypass options by default.
- Roll back only resources created by the current failed operation.
- Do not capture or persist AI output in Phase 1.
- Do not modify target-project ignore rules.

## 18. Code Style

- Python 3.11 or newer
- Type hints on public functions and Port contracts
- `dataclass(frozen=True)` for immutable value objects where appropriate
- `pathlib.Path` for filesystem paths
- Small modules with one primary responsibility
- No abstract base class when a `Protocol` is sufficient
- No generic repository, event bus, or service-locator abstraction

Representative style:

```python
@dataclass(frozen=True)
class Project:
    project_id: str
    name: str
    root: Path


class ProjectStore(Protocol):
    def find_by_root(self, root: Path) -> Project | None: ...
    def save(self, project: Project) -> None: ...
```

## 19. Testing Strategy

Runtime dependencies remain standard-library-first. `pytest` is the only planned test dependency.

### Unit tests

- Runtime-path resolution
- Registered-root and Git-root detection
- Project-ID generation
- Configuration merge and validation
- Atomic JSON state writes
- Lifecycle reconciliation
- Prompt rendering
- Adapter launch-spec generation
- CLI error translation

### Contract tests

- Every Terminal Backend implementation follows the same lifecycle contract.
- Every Agent Adapter returns a valid `LaunchSpec` and meaningful diagnostics.

### Integration tests

- Temporary `ATCODE_HOME`
- Real tmux session/window lifecycle when tmux is installed
- Nested-tmux attach behavior where practical
- Partial session creation rollback
- Development install/uninstall using a temporary `HOME`

### Mandatory no-target-artifact test

Given a temporary target project, running `init`, `start`, `status`, and `stop` must leave its file tree unchanged. All generated Runtime files must exist only under the temporary `ATCODE_HOME`.

## 20. Phase 2 Extension Path

Phase 2 adds capabilities without expanding every Phase 1 interface:

- `InteractiveBackend` for explicit input delivery
- `HandoffStore`
- `TaskQueue`
- `RelayService`
- `WorkflowService`
- `ConfigurableRoleRegistry`

`TerminalBackend` remains valid for session-only backends. A Backend supports Relay only when it separately implements `InteractiveBackend`.

State migrations are selected by `schemaVersion`. Phase 1 does not create empty Phase 2 directories or placeholder implementations.

## 21. Implementation Sequence

1. Package skeleton and thin executable entry point
2. Runtime-path resolution
3. Project discovery, registration, and `init`
4. Global/project configuration and `config`
5. Atomic state storage and locking
6. Prompt rendering
7. Adapter contract and Shell Adapter
8. Codex, Claude, and Gemini Adapters
9. Terminal Backend contract and tmux implementation
10. Session lifecycle commands
11. `doctor` and `list`
12. Install/uninstall scripts and README
13. Real tmux integration and no-target-artifact verification

Each implementation task must include its tests and touch no more than approximately five files. Verification checkpoints occur after project/configuration foundations, Adapter/Backend integration, and the complete command lifecycle.

## 22. Boundaries

### Always

- Keep AtCode artifacts under `ATCODE_HOME`.
- Validate all external inputs at the CLI, configuration, filesystem, and process boundaries.
- Run focused tests after each implementation task.
- Inspect actual Backend state before reporting lifecycle status.
- Preserve existing user Runtime configuration on idempotent operations.

### Ask first

- Add a Runtime dependency.
- Change a public command or configuration key.
- Add a Phase 2 capability to Phase 1.
- Change the target-project mutation boundary.
- Remove or migrate existing Runtime data.

### Never

- Create AtCode management files in a target project.
- Modify a target project's `.gitignore`.
- Read or modify `.env` or `.env.local`.
- Use terminal input injection or pane capture in Phase 1.
- Persist AI output, user tasks, or secrets in Phase 1 state.
- Add insecure CLI permission bypasses without an explicit future design decision.

## 23. Acceptance Criteria

Phase 1 is complete when:

1. It runs on WSL2 and native Linux with Python 3.11 or newer.
2. Git and non-Git projects can be registered.
3. No AtCode management artifact appears in a target project.
4. Each registered project has at most one AtCode tmux session.
5. The five fixed role windows launch in the canonical target root.
6. Each role can use Codex, Claude, Gemini, or Shell as configured.
7. Each AI CLI receives its initial role prompt at launch.
8. Global and project configuration merge correctly.
9. Stored state is reconciled with actual tmux state.
10. Lifecycle commands are idempotent where specified.
11. Missing CLIs fail during preflight before session creation.
12. `doctor` gives actionable environment diagnostics.
13. Uninstall preserves Runtime data by default.
14. All automated tests pass, including the mandatory no-target-artifact test.

## 24. Open Questions

None for Phase 1. Any new requirement that introduces Agent messaging, custom roles, terminal input delivery, output capture, or Workflow changes the approved Phase 1 scope and requires a design update before implementation.
