from __future__ import annotations

import re
from typing import Protocol

from pathkeeper.models import PathSnapshot

_STANDALONE_WINDOWS_VAR_PATTERN = re.compile(r"^%([^%]+)%$")


class PathReader(Protocol):
    def read_system_path(self) -> list[str]: ...

    def read_user_path(self) -> list[str]: ...

    def read_system_path_raw(self) -> str: ...

    def read_user_path_raw(self) -> str: ...


def _captured_windows_env_vars(
    entries: list[str], environment: dict[str, str] | None
) -> dict[str, str]:
    if not environment:
        return {}
    refs = {
        match.group(1)
        for entry in entries
        if (match := _STANDALONE_WINDOWS_VAR_PATTERN.fullmatch(entry.strip()))
        is not None
    }
    env_map = {name.casefold(): value for name, value in environment.items()}
    return {
        name: env_map[name.casefold()]
        for name in sorted(refs)
        if name.casefold() in env_map
    }


def read_snapshot(reader: PathReader) -> PathSnapshot:
    system_path = reader.read_system_path()
    user_path = reader.read_user_path()
    system_env_reader = getattr(reader, "read_system_environment", None)
    user_env_reader = getattr(reader, "read_user_environment", None)
    system_env = (
        _captured_windows_env_vars(system_path, system_env_reader())
        if callable(system_env_reader)
        else {}
    )
    user_env = (
        _captured_windows_env_vars(user_path, user_env_reader())
        if callable(user_env_reader)
        else {}
    )
    return PathSnapshot(
        system_path=system_path,
        user_path=user_path,
        system_path_raw=reader.read_system_path_raw(),
        user_path_raw=reader.read_user_path_raw(),
        system_env_vars=system_env,
        user_env_vars=user_env,
    )
