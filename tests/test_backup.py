from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pathkeeper.config import AppConfig, GeneralConfig
from pathkeeper.core.backup import create_backup, list_backups, prune_backups
from pathkeeper.models import BackupRecord, PathSnapshot


def _write_backup(path: Path, *, timestamp: str, tag: str) -> None:
    record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        hostname="host",
        os_name="linux",
        tag=tag,
        note="",
        system_path=["/usr/bin"],
        user_path=["/home/test/bin"],
        system_path_raw="/usr/bin",
        user_path_raw="/home/test/bin",
    )
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


def test_create_backup_uses_unique_filenames(tmp_path: Path) -> None:
    snapshot = PathSnapshot(["/usr/bin"], ["/home/test/bin"], "/usr/bin", "/home/test/bin")
    first = create_backup(snapshot, backup_dir=tmp_path, os_name="linux", tag="manual", note="")
    second = create_backup(snapshot, backup_dir=tmp_path, os_name="linux", tag="manual", note="")
    assert first != second
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_prune_backups_honors_manual_and_auto_limits(tmp_path: Path) -> None:
    _write_backup(tmp_path / "2025-03-01T10-00-00_manual.json", timestamp="2025-03-01T10:00:00Z", tag="manual")
    _write_backup(tmp_path / "2025-03-02T10-00-00_manual.json", timestamp="2025-03-02T10:00:00Z", tag="manual")
    _write_backup(tmp_path / "2025-03-03T10-00-00_auto.json", timestamp="2025-03-03T10:00:00Z", tag="auto")
    _write_backup(tmp_path / "2025-03-04T10-00-00_auto.json", timestamp="2025-03-04T10:00:00Z", tag="auto")
    _write_backup(tmp_path / "2025-03-05T10-00-00_pre-restore.json", timestamp="2025-03-05T10:00:00Z", tag="pre-restore")
    config = AppConfig(general=GeneralConfig(max_backups=3, max_auto_backups=1, max_manual_backups=1))
    prune_backups(tmp_path, config)
    remaining = [record.source_file.name for record in list_backups(tmp_path) if record.source_file is not None]
    assert remaining == [
        "2025-03-05T10-00-00_pre-restore.json",
        "2025-03-04T10-00-00_auto.json",
        "2025-03-02T10-00-00_manual.json",
    ]

