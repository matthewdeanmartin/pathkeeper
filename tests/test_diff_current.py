"""Tests for the 'pathkeeper diff-current' CLI subcommand."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig
from pathkeeper.models import BackupRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_backup(
    path: Path,
    *,
    timestamp: str,
    tag: str,
    note: str = "",
    system_path: list[str] | None = None,
    user_path: list[str] | None = None,
    os_name: str = "linux",
) -> None:
    record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        hostname="host",
        os_name=os_name,
        tag=tag,
        note=note,
        system_path=system_path or ["/usr/bin"],
        user_path=user_path or ["/home/user/bin"],
        system_path_raw=":".join(system_path or ["/usr/bin"]),
        user_path_raw=":".join(user_path or ["/home/user/bin"]),
    )
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


class _StubAdapter:
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


def _stub(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    system: list[str],
    user: list[str],
) -> None:
    monkeypatch.setattr(
        cli, "get_platform_adapter", lambda _: _StubAdapter(system, user)
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_diff_current_no_changes(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        system_path=["/usr/bin"],
        user_path=["/home/user/bin"],
    )
    _stub(monkeypatch, tmp_path, ["/usr/bin"], ["/home/user/bin"])
    exit_code = cli.run(["diff-current", "1"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No changes." in output


def test_diff_current_detects_added(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        user_path=["/home/user/bin"],
    )
    _stub(monkeypatch, tmp_path, ["/usr/bin"], ["/home/user/bin", "/opt/new"])
    exit_code = cli.run(["diff-current", "1"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "/opt/new" in output


def test_diff_current_scope_user_only(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        system_path=["/usr/bin", "/extra"],
    )
    _stub(monkeypatch, tmp_path, ["/usr/bin"], ["/home/user/bin"])
    exit_code = cli.run(["diff-current", "1", "--scope", "user"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "System PATH:" not in output
    assert "User PATH:" in output


def test_diff_current_no_backups(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _stub(monkeypatch, tmp_path, ["/usr/bin"], ["/home/user/bin"])
    # Provide identifier "1" to skip interactive prompt
    exit_code = cli.main(["diff-current", "1"])
    assert exit_code != 0
