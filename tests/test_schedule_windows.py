from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from pathkeeper.core.schedule import install_schedule


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
def test_install_schedule_windows_logon_uses_powershell(monkeypatch):
    from pathkeeper.core import schedule

    # Mock _run to capture the command
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    monkeypatch.setattr(schedule, "_run", mock_run)

    # Mock os.environ to have a known USERNAME
    monkeypatch.setenv("USERNAME", "testuser")

    # Run install_schedule with logon trigger
    result = install_schedule("windows", "startup", trigger="logon")

    assert "Installed Windows scheduled task for user logon." in result

    # Check that powershell was called
    args, _kwargs = mock_run.call_args
    command = args[0]
    assert command[0] == "powershell"
    assert "Register-ScheduledTask" in command[-1]
    assert "-AtLogOn" in command[-1]
    assert "-User 'testuser'" in command[-1]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
def test_install_schedule_windows_startup_uses_schtasks(monkeypatch):
    from pathkeeper.core import schedule

    # Mock _run to capture the command
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    monkeypatch.setattr(schedule, "_run", mock_run)

    # Run install_schedule with startup trigger
    result = install_schedule("windows", "startup", trigger="startup")

    assert "Installed Windows scheduled task." in result

    # Check that schtasks was called
    args, _kwargs = mock_run.call_args
    command = args[0]
    assert command[0] == "schtasks"
    assert "/SC" in command
    assert "ONSTART" in command


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only tests")
def test_install_schedule_windows_minute_uses_schtasks(monkeypatch):
    from pathkeeper.core import schedule

    # Mock _run to capture the command
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    monkeypatch.setattr(schedule, "_run", mock_run)

    # Run install_schedule with minute interval
    result = install_schedule("windows", "60m", trigger="startup")

    assert "Installed Windows scheduled task." in result

    # Check that schtasks was called
    args, _kwargs = mock_run.call_args
    command = args[0]
    assert command[0] == "schtasks"
    assert "/SC" in command
    assert "MINUTE" in command
    assert "/MO" in command
    assert "60" in command
