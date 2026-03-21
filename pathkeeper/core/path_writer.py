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

