from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pathkeeper.core.repair_truncated import find_truncated_repairs
from pathkeeper.models import BackupRecord, PathSnapshot, Scope


def _backup_record(*, user_path: list[str]) -> BackupRecord:
    return BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat("2025-03-02T11:00:00+00:00"),
        hostname="host",
        os_name="windows",
        tag="manual",
        note="",
        system_path=[],
        user_path=user_path,
        system_path_raw="",
        user_path_raw=";".join(user_path),
        source_file=Path("2025-03-02T11-00-00_manual.json"),
    )


def test_find_truncated_repairs_uses_backup_suffix_matches(tmp_path: Path) -> None:
    full_dir = (
        tmp_path
        / "Users"
        / "matth"
        / "AppData"
        / "Local"
        / "Programs"
        / "Python"
        / "Python314"
        / "Scripts"
    )
    full_dir.mkdir(parents=True)
    snapshot = PathSnapshot(
        system_path=[],
        user_path=[
            "Users\\matth\\AppData\\Local\\Programs\\Python\\Python314\\Scripts"
        ],
        system_path_raw="",
        user_path_raw="Users\\matth\\AppData\\Local\\Programs\\Python\\Python314\\Scripts",
    )
    repairs = find_truncated_repairs(
        snapshot=snapshot,
        scope=Scope.USER,
        os_name="windows",
        records=[_backup_record(user_path=[str(full_dir)])],
        search_roots=[],
    )
    assert len(repairs) == 1
    assert (
        repairs[0].value
        == "Users\\matth\\AppData\\Local\\Programs\\Python\\Python314\\Scripts"
    )
    assert repairs[0].candidates[0].path == str(full_dir)
    assert repairs[0].candidates[0].source.startswith("backup ")


def test_find_truncated_repairs_can_search_disk_roots(tmp_path: Path) -> None:
    full_dir = tmp_path / "Programs" / "Example" / "bin"
    full_dir.mkdir(parents=True)
    snapshot = PathSnapshot(
        system_path=[],
        user_path=["Example\\bin"],
        system_path_raw="",
        user_path_raw="Example\\bin",
    )
    repairs = find_truncated_repairs(
        snapshot=snapshot,
        scope=Scope.USER,
        os_name="windows",
        records=[],
        search_roots=[tmp_path],
    )
    assert len(repairs) == 1
    assert repairs[0].candidates[0].path == str(full_dir)
    assert repairs[0].candidates[0].source.startswith("disk ")
