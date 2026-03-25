from __future__ import annotations

from typing import Protocol

from pathkeeper.errors import PathkeeperError
from pathkeeper.models import PathSnapshot, Scope


class PathWriter(Protocol):
    def write_system_path(self, entries: list[str]) -> None: ...

    def write_user_path(self, entries: list[str]) -> None: ...


class EnvironmentVariableWriter(Protocol):
    def write_system_env_var(self, name: str, value: str) -> None: ...

    def write_user_env_var(self, name: str, value: str) -> None: ...

    def delete_system_env_var(self, name: str) -> None: ...

    def delete_user_env_var(self, name: str) -> None: ...


def write_snapshot(writer: PathWriter, snapshot: PathSnapshot, scope: Scope) -> None:
    if scope in {Scope.SYSTEM, Scope.ALL}:
        writer.write_system_path(snapshot.system_path)
    if scope in {Scope.USER, Scope.ALL}:
        writer.write_user_path(snapshot.user_path)
    write_changed_environment(writer, PathSnapshot([], [], "", ""), snapshot, scope)


def write_changed_snapshot(
    writer: PathWriter, current: PathSnapshot, updated: PathSnapshot, scope: Scope
) -> None:
    if (
        scope in {Scope.SYSTEM, Scope.ALL}
        and current.system_path != updated.system_path
    ):
        writer.write_system_path(updated.system_path)
    if scope in {Scope.USER, Scope.ALL} and current.user_path != updated.user_path:
        writer.write_user_path(updated.user_path)
    write_changed_environment(writer, current, updated, scope)


def write_changed_environment(
    writer: object, current: PathSnapshot, updated: PathSnapshot, scope: Scope
) -> None:
    required = (
        "write_system_env_var",
        "write_user_env_var",
        "delete_system_env_var",
        "delete_user_env_var",
    )
    if not any(
        current.env_vars_for_scope(candidate) != updated.env_vars_for_scope(candidate)
        for candidate in (Scope.SYSTEM, Scope.USER)
        if scope in {candidate, Scope.ALL}
    ):
        return
    if not all(hasattr(writer, name) for name in required):
        raise PathkeeperError(
            "This platform adapter cannot write PATH helper variables."
        )
    env_writer = writer
    if scope in {Scope.SYSTEM, Scope.ALL}:
        _write_scope_environment(
            env_writer,
            current.system_env_vars,
            updated.system_env_vars,
            write_name="write_system_env_var",
            delete_name="delete_system_env_var",
        )
    if scope in {Scope.USER, Scope.ALL}:
        _write_scope_environment(
            env_writer,
            current.user_env_vars,
            updated.user_env_vars,
            write_name="write_user_env_var",
            delete_name="delete_user_env_var",
        )


def _write_scope_environment(
    writer: object,
    current: dict[str, str],
    updated: dict[str, str],
    *,
    write_name: str,
    delete_name: str,
) -> None:
    write_env = getattr(writer, write_name)
    delete_env = getattr(writer, delete_name)
    for name in sorted(updated):
        if current.get(name) != updated[name]:
            write_env(name, updated[name])
    for name in sorted(set(current) - set(updated)):
        delete_env(name)
