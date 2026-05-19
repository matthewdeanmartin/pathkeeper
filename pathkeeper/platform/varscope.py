"""Adapter that reads/writes an arbitrary environment variable instead of PATH.

Used with --var <NAME> to let callers manage PATHX (or any other variable) with
all the same pathkeeper commands without touching the real PATH.
"""

from __future__ import annotations

import os

from pathkeeper.core.diagnostics import join_path, split_path


class EnvVarAdapter:
    """Treats a named environment variable as both user and system PATH."""

    os_name: str

    def __init__(self, var_name: str, os_name: str) -> None:
        self._var_name = var_name
        self.os_name = os_name

    def _raw(self) -> str:
        return os.environ.get(self._var_name, "")

    def read_system_path(self) -> list[str]:
        return []

    def read_system_path_raw(self) -> str:
        return ""

    def read_user_path(self) -> list[str]:
        return split_path(self._raw(), self.os_name)

    def read_user_path_raw(self) -> str:
        return self._raw()

    def write_user_path(self, entries: list[str]) -> None:
        os.environ[self._var_name] = join_path(entries, self.os_name)

    def write_system_path(self, entries: list[str]) -> None:
        pass

    def read_system_environment(self) -> dict[str, str]:
        return {}

    def read_user_environment(self) -> dict[str, str]:
        return dict(os.environ)
