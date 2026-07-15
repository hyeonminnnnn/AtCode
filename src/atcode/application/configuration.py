"""Validated global and per-project Runtime configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from atcode.domain.errors import AtCodeError
from atcode.domain.models import Layout, Project, Role, RoleAssignment, RuntimeConfig
from atcode.ports.storage import ConfigurationStore

_DEFAULT: dict[str, Any] = {
    "schemaVersion": 1,
    "backend": "tmux",
    "layout": "panes",
    "roles": {
        "pm": {"adapter": "codex"},
        "developer": {"adapter": "codex"},
        "reviewer": {"adapter": "codex"},
    },
}

_LEGACY_ROLES = frozenset({"tester", "docs"})


class ConfigurationService:
    def __init__(
        self,
        store: ConfigurationStore,
        *,
        allowed_backends: set[str],
        allowed_adapters: set[str],
    ) -> None:
        self._store = store
        self._backends = allowed_backends
        self._adapters = allowed_adapters

    def effective(self, project: Project | None) -> RuntimeConfig:
        try:
            layers = [self._store.read_global()]
            if project is not None:
                layers.append(self._store.read_project(project))
            merged = deepcopy(_DEFAULT)
            for layer in layers:
                normalized = self._normalize_legacy_roles(layer)
                self._validate_layer(normalized)
                merged = _merge(merged, normalized)
            self._validate_layer(merged, complete=True)
            return RuntimeConfig(
                backend=merged["backend"],
                roles={
                    role: RoleAssignment(merged["roles"][role.value]["adapter"])
                    for role in Role
                },
                layout=Layout(merged["layout"]),
            )
        except AtCodeError:
            raise
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "CONFIG_INVALID",
                "Runtime configuration is invalid.",
                hint="Inspect the global and project config.json files.",
                exit_code=2,
            ) from error

    def get(self, project: Project | None, key: str) -> str:
        self._validate_key(key)
        config = self.effective(project)
        if key == "backend":
            return config.backend
        if key == "layout":
            return config.layout.value
        role = Role(key.split(".")[1])
        return config.roles[role].adapter

    def set(
        self,
        project: Project | None,
        key: str,
        value: str,
        *,
        global_scope: bool,
    ) -> None:
        self._validate_key(key)
        self._validate_value(key, value)
        current = self._read_target(project, global_scope)
        if key in {"backend", "layout"}:
            current[key] = value
        else:
            role = key.split(".")[1]
            current.setdefault("roles", {}).setdefault(role, {})["adapter"] = value
        self._validate_layer(current)
        self._write_target(project, global_scope, current)

    def unset(
        self,
        project: Project | None,
        key: str,
        *,
        global_scope: bool,
    ) -> None:
        self._validate_key(key)
        current = self._read_target(project, global_scope)
        if key in {"backend", "layout"}:
            current.pop(key, None)
        else:
            role = key.split(".")[1]
            roles = current.get("roles", {})
            roles.get(role, {}).pop("adapter", None)
            if role in roles and not roles[role]:
                roles.pop(role)
            if not roles:
                current.pop("roles", None)
        self._write_target(project, global_scope, current)

    def _read_target(
        self,
        project: Project | None,
        global_scope: bool,
    ) -> dict[str, Any]:
        try:
            if global_scope:
                return self._normalize_legacy_roles(self._store.read_global())
            if project is None:
                raise AtCodeError(
                    "PROJECT_REQUIRED",
                    "A project is required.",
                    exit_code=2,
                )
            return self._normalize_legacy_roles(self._store.read_project(project))
        except AtCodeError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise AtCodeError(
                "CONFIG_INVALID",
                "Runtime configuration is invalid.",
                hint="Inspect the global and project config.json files.",
                exit_code=2,
            ) from error

    def _write_target(
        self,
        project: Project | None,
        global_scope: bool,
        value: dict[str, Any],
    ) -> None:
        if global_scope:
            self._store.write_global(value)
        elif project is not None:
            self._store.write_project(project, value)

    def _validate_key(self, key: str) -> None:
        valid = {"backend", "layout"} | {
            f"roles.{role.value}.adapter" for role in Role
        }
        if key not in valid:
            raise AtCodeError(
                "CONFIG_KEY_INVALID",
                f"Unsupported configuration key: {key}",
                exit_code=2,
            )

    def _validate_value(self, key: str, value: str) -> None:
        if key == "backend":
            allowed = self._backends
        elif key == "layout":
            allowed = {layout.value for layout in Layout}
        else:
            allowed = self._adapters
        if value not in allowed:
            raise AtCodeError(
                "CONFIG_VALUE_INVALID",
                f"Unsupported value for {key}: {value}",
                exit_code=2,
            )

    def _validate_layer(self, value: dict[str, Any], complete: bool = False) -> None:
        if not isinstance(value, dict):
            raise AtCodeError("CONFIG_INVALID", "Configuration must be an object.")
        if value.get("schemaVersion") != 1 or set(value) - {
            "schemaVersion",
            "backend",
            "layout",
            "roles",
        }:
            raise AtCodeError("CONFIG_INVALID", "Invalid configuration object.")
        if "backend" in value:
            self._validate_value("backend", value["backend"])
        if "layout" in value:
            self._validate_value("layout", value["layout"])
        roles = value.get("roles", {})
        if not isinstance(roles, dict):
            raise AtCodeError("CONFIG_INVALID", "roles must be an object.")
        for role_name, assignment in roles.items():
            if role_name not in {role.value for role in Role}:
                raise AtCodeError("CONFIG_INVALID", f"Unknown role: {role_name}")
            self._validate_assignment(role_name, assignment)
        if complete and set(roles) != {role.value for role in Role}:
            raise AtCodeError("CONFIG_INVALID", "Every Phase 1 role is required.")

    def _normalize_legacy_roles(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise AtCodeError("CONFIG_INVALID", "Configuration must be an object.")
        normalized = deepcopy(value)
        roles = normalized.get("roles")
        if not isinstance(roles, dict):
            return normalized
        for role_name in _LEGACY_ROLES:
            if role_name in roles:
                self._validate_assignment(role_name, roles[role_name])
                roles.pop(role_name)
        return normalized

    def _validate_assignment(self, role_name: str, assignment: Any) -> None:
        if not isinstance(assignment, dict) or set(assignment) != {"adapter"}:
            raise AtCodeError("CONFIG_INVALID", f"Invalid role: {role_name}")
        self._validate_value(
            f"roles.{role_name}.adapter",
            assignment["adapter"],
        )


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged
