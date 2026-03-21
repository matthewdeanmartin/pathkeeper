from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig


class StubAdapter:
    def __init__(self, system: list[str], user: list[str]) -> None:
        self._system = system
        self._user = user

    def read_system_path(self) -> list[str]:
        return list(self._system)

    def read_user_path(self) -> list[str]:
        return list(self._user)

    def read_system_path_raw(self) -> str:
        return ":".join(self._system)

    def read_user_path_raw(self) -> str:
        return ":".join(self._user)

    def write_system_path(self, entries: list[str]) -> None:
        self._system = list(entries)

    def write_user_path(self, entries: list[str]) -> None:
        self._user = list(entries)


def test_doctor_json_output(monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/missing", "/usr/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["summary"]["duplicates"] == 1
    assert payload["summary"]["invalid"] >= 1


def test_backup_command_writes_to_overridden_backup_home(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["backup"])
    assert exit_code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert "Created backup:" in capsys.readouterr().out

