from __future__ import annotations

from typing import Protocol

from pathkeeper.models import PathSnapshot


class PathReader(Protocol):
    def read_system_path(self) -> list[str]: ...

    def read_user_path(self) -> list[str]: ...

    def read_system_path_raw(self) -> str: ...

    def read_user_path_raw(self) -> str: ...


def read_snapshot(reader: PathReader) -> PathSnapshot:
    return PathSnapshot(
        system_path=reader.read_system_path(),
        user_path=reader.read_user_path(),
        system_path_raw=reader.read_system_path_raw(),
        user_path_raw=reader.read_user_path_raw(),
    )

