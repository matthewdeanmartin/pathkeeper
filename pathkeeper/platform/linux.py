from __future__ import annotations

from pathkeeper.core.diagnostics import join_path
from pathkeeper.errors import PermissionDeniedError
from pathkeeper.platform.unix_common import UnixPlatformBase


class LinuxPlatform(UnixPlatformBase):
    os_name = "linux"
    system_path_file_name = "/etc/environment"

    def read_system_path_raw(self) -> str:
        if not self._system_path_file.exists():
            return ""
        for line in self._system_path_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("PATH="):
                return stripped.removeprefix("PATH=").strip().strip('"')
        return ""

    def write_system_path(self, entries: list[str]) -> None:
        lines: list[str] = []
        if self._system_path_file.exists():
            lines = self._system_path_file.read_text(encoding="utf-8").splitlines()
        rendered = f'PATH="{join_path(entries, self.os_name)}"'
        updated: list[str] = []
        replaced = False
        for line in lines:
            if line.strip().startswith("PATH="):
                updated.append(rendered)
                replaced = True
            else:
                updated.append(line)
        if not replaced:
            updated.append(rendered)
        try:
            self._system_path_file.parent.mkdir(parents=True, exist_ok=True)
            self._system_path_file.write_text(
                "\n".join(updated) + "\n", encoding="utf-8"
            )
        except PermissionError as error:
            raise PermissionDeniedError(str(error)) from error
