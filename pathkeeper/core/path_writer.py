from __future__ import annotations

from typing import Protocol

from pathkeeper.models import PathSnapshot, Scope


class PathWriter(Protocol):
    def write_system_path(self, entries: list[str]) -> None: ...

    def write_user_path(self, entries: list[str]) -> None: ...


def write_snapshot(writer: PathWriter, snapshot: PathSnapshot, scope: Scope) -> None:
    if scope in {Scope.SYSTEM, Scope.ALL}:
        writer.write_system_path(snapshot.system_path)
    if scope in {Scope.USER, Scope.ALL}:
        writer.write_user_path(snapshot.user_path)


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
