from __future__ import annotations

import sys

from pathkeeper.config import AppConfig
from pathkeeper.platform.linux import LinuxPlatform
from pathkeeper.platform.macos import MacOSPlatform
from pathkeeper.platform.varscope import EnvVarAdapter
from pathkeeper.platform.windows import WindowsPlatform


def normalized_os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def get_platform_adapter(
    config: AppConfig,
    var_name: str = "PATH",
) -> WindowsPlatform | LinuxPlatform | MacOSPlatform | EnvVarAdapter:
    os_name = normalized_os_name()
    if var_name != "PATH":
        return EnvVarAdapter(var_name, os_name)
    if os_name == "windows":
        return WindowsPlatform()
    if os_name == "darwin":
        return MacOSPlatform(rc_file_override=config.shell.rc_file or None)
    return LinuxPlatform(rc_file_override=config.shell.rc_file or None)
