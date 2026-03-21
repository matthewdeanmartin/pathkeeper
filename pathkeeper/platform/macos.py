from __future__ import annotations

from pathkeeper.errors import PermissionDeniedError
from pathkeeper.platform.unix_common import UnixPlatformBase


class MacOSPlatform(UnixPlatformBase):
    os_name = "darwin"
    system_path_file_name = "/etc/paths"

    def read_system_path_raw(self) -> str:
        if not self._system_path_file.exists():
            return ""
        entries = [
            line.strip()
            for line in self._system_path_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return ":".join(entries)

    def write_system_path(self, entries: list[str]) -> None:
        content = "\n".join(entry for entry in entries if entry) + "\n"
        try:
            self._system_path_file.parent.mkdir(parents=True, exist_ok=True)
            self._system_path_file.write_text(content, encoding="utf-8")
        except PermissionError as error:
            raise PermissionDeniedError(str(error)) from error

