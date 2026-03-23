from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from pathkeeper.core.diagnostics import join_path, split_path
from pathkeeper.errors import PermissionDeniedError

MANAGED_MARKER = "# --- pathkeeper managed ---"


class UnixPlatformBase:
    os_name = "linux"
    system_path_file_name = "/etc/environment"

    def __init__(
        self,
        *,
        rc_file_override: str | None = None,
        environ: Mapping[str, str] | None = None,
        system_path_file: Path | None = None,
    ) -> None:
        self._environ = dict(environ or os.environ)
        self._system_path_file = system_path_file or Path(self.system_path_file_name)
        self._rc_file = (
            Path(rc_file_override).expanduser()
            if rc_file_override
            else self._detect_rc_file()
        )

    def _detect_rc_file(self) -> Path:
        shell = self._environ.get("SHELL", "")
        home = Path.home()
        if shell.endswith("zsh"):
            return home / ".zshrc"
        if shell.endswith("fish"):
            return home / ".config" / "fish" / "config.fish"
        return home / ".bashrc"

    def read_system_path(self) -> list[str]:
        return split_path(self.read_system_path_raw(), self.os_name)

    def read_system_path_raw(self) -> str:
        raise NotImplementedError

    def read_user_path(self) -> list[str]:
        managed = self._read_managed_entries()
        if managed:
            return managed
        return split_path(self._environ.get("PATH", ""), self.os_name)

    def read_user_path_raw(self) -> str:
        managed = self._read_managed_entries()
        if managed:
            return join_path(managed, self.os_name)
        return self._environ.get("PATH", "")

    def write_user_path(self, entries: list[str]) -> None:
        self._rc_file.parent.mkdir(parents=True, exist_ok=True)
        content = (
            self._rc_file.read_text(encoding="utf-8") if self._rc_file.exists() else ""
        )
        block = self._render_managed_block(entries)
        if MANAGED_MARKER in content:
            before, _, tail = content.partition(MANAGED_MARKER)
            _, _, after = tail.partition(MANAGED_MARKER)
            updated = f"{before}{block}{after}"
        else:
            suffix = "\n" if content and not content.endswith("\n") else ""
            updated = f"{content}{suffix}{block}"
        try:
            self._rc_file.write_text(updated, encoding="utf-8")
        except PermissionError as error:
            raise PermissionDeniedError(str(error)) from error

    def _render_managed_block(self, entries: list[str]) -> str:
        joined = join_path(entries, self.os_name)
        if self._rc_file.name == "config.fish":
            path_values = " ".join(f'"{entry}"' for entry in entries)
            body = f"set -gx PATH {path_values}\n" if entries else "set -e PATH\n"
        else:
            body = f'export PATH="{joined}"\n'
        return f"{MANAGED_MARKER}\n{body}{MANAGED_MARKER}\n"

    def _read_managed_entries(self) -> list[str]:
        if not self._rc_file.exists():
            return []
        content = self._rc_file.read_text(encoding="utf-8")
        if MANAGED_MARKER not in content:
            return []
        _, _, tail = content.partition(MANAGED_MARKER)
        block, _, _ = tail.partition(MANAGED_MARKER)
        return self._parse_managed_block(block)

    def _parse_managed_block(self, block: str) -> list[str]:
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("export PATH="):
                value = stripped.removeprefix("export PATH=").strip().strip('"')
                return split_path(value, self.os_name)
            if stripped.startswith("set -gx PATH "):
                payload = stripped.removeprefix("set -gx PATH ").strip()
                return [part.strip('"') for part in payload.split()]
        return []
