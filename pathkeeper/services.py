"""Shared service layer used by both CLI and GUI.

This module provides orchestration helpers that load config, read snapshots,
and coordinate core modules.  Neither ``cli`` nor ``gui`` should duplicate
this logic.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pathkeeper.config import backups_home, load_config
from pathkeeper.core.backup import (
    _load_latest_backup,
    backup_content_hash,
    backup_filename,
    create_backup,
    list_backups,
    prune_backups,
    resolve_backup,
)
from pathkeeper.core.path_reader import read_snapshot
from pathkeeper.errors import PathkeeperError
from pathkeeper.models import Scope
from pathkeeper.platform import get_platform_adapter, normalized_os_name

if TYPE_CHECKING:
    from pathkeeper.models import BackupRecord, DiagnosticReport, PathSnapshot
    from pathkeeper.core.path_writer import PathWriter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Snapshot & adapter helpers
# ------------------------------------------------------------------

def get_snapshot_and_adapter() -> "tuple[PathSnapshot, PathWriter, str]":
    """Return (snapshot, platform_adapter, os_name)."""
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    return snapshot, adapter, os_name


# ------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------

def read_current_report(scope: Scope) -> tuple["PathSnapshot", "DiagnosticReport"]:
    """Read the live PATH and return a diagnostic report."""
    from pathkeeper.core.diagnostics import analyze_snapshot

    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    report = analyze_snapshot(
        system_entries=snapshot.system_path,
        user_entries=snapshot.user_path,
        os_name=normalized_os_name(),
        scope=scope,
        raw_value=snapshot.raw_for_scope(scope),
    )
    return snapshot, report


# ------------------------------------------------------------------
# Backups
# ------------------------------------------------------------------

def recent_backups(*, limit: int = 20) -> list["BackupRecord"]:
    return list_backups(backups_home())[:limit]


def select_backup(identifier: str | None) -> tuple["BackupRecord", list["BackupRecord"]]:
    records = list_backups(backups_home())
    if not records:
        raise PathkeeperError("No backups available.")
    if identifier:
        if identifier.isdigit():
            selection = int(identifier)
            recent = records[:20]
            if 1 <= selection <= len(recent):
                return recent[selection - 1], records
            raise PathkeeperError(f"Backup selection out of range: {identifier}")
        return resolve_backup(identifier, backups_home()), records
    return records[0], records


def backup_now(*, tag: str, note: str, force: bool = False) -> Path | None:
    """Create a backup and prune.  Return the backup path, or None if skipped."""
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    backup_dir = backups_home()
    destination, all_records = create_backup(
        snapshot,
        backup_dir=backup_dir,
        os_name=normalized_os_name(),
        tag=tag,
        note=note,
        force=force,
    )
    if destination is None:
        return None
    prune_backups(backup_dir, config, all_records)
    return destination


def format_backup_timestamp_utc(value: datetime) -> str:
    timestamp = value.astimezone(UTC)
    return timestamp.strftime("%Y-%m-%d %H:%MZ")
