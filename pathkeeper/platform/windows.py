from __future__ import annotations

import ctypes
import os
import sys
from typing import Any

from pathkeeper.core.diagnostics import split_path
from pathkeeper.errors import PermissionDeniedError

if sys.platform == "win32":
    import winreg as _winreg
    _WINREG: Any = _winreg
else:
    _WINREG: Any = None  # type: ignore[no-redef]


SYSTEM_KEY = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"
USER_KEY = r"Environment"
REG_PATH_VALUE = "Path"
HWND_BROADCAST = 0xFFFF
WM_SETTINGCHANGE = 0x001A
SMTO_ABORTIFHUNG = 0x0002


class WindowsPlatform:
    os_name = "windows"

    def __init__(self) -> None:
        if _WINREG is None:
            self._fallback_raw = os.environ.get("PATH", "")
        self._registry_cache: dict[str, tuple[list[str], str]] = {}

    # Registry reads are cached per-instance so that read_system_path() and
    # read_system_path_raw() (and the user equivalents) each open the key once
    # rather than twice.  The cache is intentionally not invalidated — a
    # PathSnapshot is a point-in-time object and the adapter is created fresh
    # for each command invocation.
    def _read_registry(self, root: Any, key_name: str) -> tuple[list[str], str]:
        if key_name in self._registry_cache:
            return self._registry_cache[key_name]
        if _WINREG is None:
            result: tuple[list[str], str] = (split_path(self._fallback_raw, self.os_name), self._fallback_raw)
        else:
            with _WINREG.OpenKey(root, key_name) as key:
                value, _value_type = _WINREG.QueryValueEx(key, REG_PATH_VALUE)
            raw = str(value)
            result = (split_path(raw, self.os_name), raw)
        self._registry_cache[key_name] = result
        return result

    def read_system_path(self) -> list[str]:
        return self._read_registry(_WINREG.HKEY_LOCAL_MACHINE if _WINREG else object(), SYSTEM_KEY)[0]

    def read_user_path(self) -> list[str]:
        return self._read_registry(_WINREG.HKEY_CURRENT_USER if _WINREG else object(), USER_KEY)[0]

    def read_system_path_raw(self) -> str:
        return self._read_registry(_WINREG.HKEY_LOCAL_MACHINE if _WINREG else object(), SYSTEM_KEY)[1]

    def read_user_path_raw(self) -> str:
        return self._read_registry(_WINREG.HKEY_CURRENT_USER if _WINREG else object(), USER_KEY)[1]

    def _write_registry(self, root: Any, key_name: str, entries: list[str]) -> None:
        raw = ";".join(entries)
        if _WINREG is None:
            self._fallback_raw = raw
            return
        try:
            with _WINREG.OpenKey(root, key_name, 0, _WINREG.KEY_SET_VALUE) as key:
                _WINREG.SetValueEx(key, REG_PATH_VALUE, 0, _WINREG.REG_EXPAND_SZ, raw)
        except PermissionError as error:
            scope_name = "system" if key_name == SYSTEM_KEY else "user"
            raise PermissionDeniedError(
                f"Access denied writing the {scope_name} PATH. Re-run from an elevated shell "
                "or limit the operation to a writable scope."
            ) from error
        self._broadcast_change()

    def write_system_path(self, entries: list[str]) -> None:
        self._write_registry(_WINREG.HKEY_LOCAL_MACHINE if _WINREG else object(), SYSTEM_KEY, entries)

    def write_user_path(self, entries: list[str]) -> None:
        self._write_registry(_WINREG.HKEY_CURRENT_USER if _WINREG else object(), USER_KEY, entries)

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

