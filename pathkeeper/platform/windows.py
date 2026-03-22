from __future__ import annotations

import ctypes
import os
from typing import Any

from pathkeeper.core.diagnostics import split_path
from pathkeeper.errors import PermissionDeniedError

try:
    import winreg
except ImportError:  # pragma: no cover - exercised on non-Windows platforms
    winreg = None  # type: ignore[assignment]


SYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
USER_KEY = r"Environment"
REG_PATH_VALUE = "Path"
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


class WindowsPlatform:
    os_name = "windows"

    def __init__(self) -> None:
        if winreg is None:
            self._fallback_raw = os.environ.get("PATH", "")

    def _read_registry(self, root: Any, key_name: str) -> tuple[list[str], str]:
        if winreg is None:
            return split_path(self._fallback_raw, self.os_name), self._fallback_raw
        with winreg.OpenKey(root, key_name) as key:
            value, _value_type = winreg.QueryValueEx(key, REG_PATH_VALUE)
        raw = str(value)
        return split_path(raw, self.os_name), raw

    def read_system_path(self) -> list[str]:
        return self._read_registry(winreg.HKEY_LOCAL_MACHINE if winreg else object(), SYSTEM_KEY)[0]

    def read_user_path(self) -> list[str]:
        return self._read_registry(winreg.HKEY_CURRENT_USER if winreg else object(), USER_KEY)[0]

    def read_system_path_raw(self) -> str:
        return self._read_registry(winreg.HKEY_LOCAL_MACHINE if winreg else object(), SYSTEM_KEY)[1]

    def read_user_path_raw(self) -> str:
        return self._read_registry(winreg.HKEY_CURRENT_USER if winreg else object(), USER_KEY)[1]

    def _write_registry(self, root: Any, key_name: str, entries: list[str]) -> None:
        raw = ";".join(entries)
        if winreg is None:
            self._fallback_raw = raw
            return
        try:
            with winreg.OpenKey(root, key_name, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, REG_PATH_VALUE, 0, winreg.REG_EXPAND_SZ, raw)
        except PermissionError as error:
            scope_name = "system" if key_name == SYSTEM_KEY else "user"
            raise PermissionDeniedError(
                f"Access denied writing the {scope_name} PATH. Re-run from an elevated shell "
                "or limit the operation to a writable scope."
            ) from error
        self._broadcast_change()

    def write_system_path(self, entries: list[str]) -> None:
        self._write_registry(winreg.HKEY_LOCAL_MACHINE if winreg else object(), SYSTEM_KEY, entries)

    def write_user_path(self, entries: list[str]) -> None:
        self._write_registry(winreg.HKEY_CURRENT_USER if winreg else object(), USER_KEY, entries)

    def ensure_system_writable(self) -> None:
        if os.name != "nt":
            return
        try:
            is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError) as error:
            raise PermissionDeniedError(
                "Unable to determine whether the system PATH is writable. "
                "Re-run from an elevated shell or limit the operation to a writable scope."
            ) from error
        if not is_admin:
            raise PermissionDeniedError(
                "Access denied writing the system PATH. Re-run from an elevated shell "
                "or limit the operation to a writable scope."
            )

    def _broadcast_change(self) -> None:
        if os.name != "nt":
            return
        send_message_timeout = ctypes.windll.user32.SendMessageTimeoutW
        send_message_timeout(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None)

