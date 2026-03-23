from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pathkeeper.errors import PathkeeperError, PermissionDeniedError


@dataclass(frozen=True)
class ScheduleStatus:
    enabled: bool
    detail: str


def _command_line() -> str:
    return f'"{sys.executable}" -m pathkeeper backup --tag auto --quiet'


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _clean_windows_task_error(text: str) -> str:
    cleaned = text.strip()
    while cleaned.upper().startswith("ERROR:"):
        cleaned = cleaned[6:].strip()
    return cleaned


def schedule_status(os_name: str) -> ScheduleStatus:
    if os_name == "windows":
        result = _run(["schtasks", "/Query", "/TN", "pathkeeper"])
        return ScheduleStatus(
            result.returncode == 0, result.stdout.strip() or result.stderr.strip()
        )
    if os_name == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.pathkeeper.backup.plist"
        return ScheduleStatus(plist.exists(), str(plist))
    timer = Path.home() / ".config" / "systemd" / "user" / "pathkeeper.timer"
    cron = Path.home() / ".pathkeeper" / "pathkeeper.cron"
    return ScheduleStatus(
        timer.exists() or cron.exists(), str(timer if timer.exists() else cron)
    )


def install_schedule(os_name: str, interval: str, *, trigger: str = "startup") -> str:
    if os_name == "windows":
        schedule = "ONSTART" if trigger == "startup" else "ONLOGON"
        if interval != "startup" and trigger == "startup":
            schedule = "MINUTE"
        command = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            "pathkeeper",
            "/TR",
            _command_line(),
            "/SC",
            schedule,
        ]
        if interval != "startup" and schedule == "MINUTE":
            command.extend(["/MO", interval.removesuffix("m")])
        result = _run(command)
        if result.returncode != 0:
            detail = _clean_windows_task_error(
                result.stderr
                or result.stdout
                or "Failed to install Windows scheduled task."
            )
            if "access is denied" in detail.lower():
                raise PermissionDeniedError(detail)
            raise PathkeeperError(detail)
        if trigger == "logon":
            return "Installed Windows scheduled task for user logon."
        return "Installed Windows scheduled task."
    if os_name == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.pathkeeper.backup.plist"
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_text(
            "\n".join(
                [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
                    '<plist version="1.0">',
                    "<dict>",
                    "  <key>Label</key>",
                    "  <string>com.pathkeeper.backup</string>",
                    "  <key>ProgramArguments</key>",
                    "  <array>",
                    f"    <string>{sys.executable}</string>",
                    "    <string>-m</string>",
                    "    <string>pathkeeper</string>",
                    "    <string>backup</string>",
                    "    <string>--tag</string>",
                    "    <string>auto</string>",
                    "    <string>--quiet</string>",
                    "  </array>",
                    "  <key>RunAtLoad</key>",
                    "  <true/>",
                    "</dict>",
                    "</plist>",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        if shutil.which("launchctl"):
            _run(["launchctl", "load", str(plist)])
        return f"Installed launchd agent at {plist}."
    timer_dir = Path.home() / ".config" / "systemd" / "user"
    timer_dir.mkdir(parents=True, exist_ok=True)
    service = timer_dir / "pathkeeper.service"
    timer = timer_dir / "pathkeeper.timer"
    service.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Run pathkeeper backup",
                "",
                "[Service]",
                "Type=oneshot",
                f"ExecStart={_command_line()}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    timer.write_text(
        "\n".join(
            [
                "[Unit]",
                "Description=Schedule pathkeeper backups",
                "",
                "[Timer]",
                "OnBootSec=1min",
                "OnUnitActiveSec=1h" if interval != "startup" else "Persistent=true",
                "",
                "[Install]",
                "WantedBy=timers.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    if shutil.which("systemctl"):
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", "pathkeeper.timer"])
    return f"Installed systemd user timer at {timer}."


def remove_schedule(os_name: str) -> str:
    if os_name == "windows":
        result = _run(["schtasks", "/Delete", "/F", "/TN", "pathkeeper"])
        if result.returncode != 0:
            raise PathkeeperError(
                result.stderr.strip() or "Failed to remove Windows scheduled task."
            )
        return "Removed Windows scheduled task."
    if os_name == "darwin":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.pathkeeper.backup.plist"
        if shutil.which("launchctl") and plist.exists():
            _run(["launchctl", "unload", str(plist)])
        plist.unlink(missing_ok=True)
        return f"Removed {plist}."
    timer_dir = Path.home() / ".config" / "systemd" / "user"
    for path in (timer_dir / "pathkeeper.timer", timer_dir / "pathkeeper.service"):
        path.unlink(missing_ok=True)
    if shutil.which("systemctl"):
        _run(["systemctl", "--user", "disable", "--now", "pathkeeper.timer"])
        _run(["systemctl", "--user", "daemon-reload"])
    return "Removed Linux schedule files."
