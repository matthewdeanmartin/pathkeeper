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
    from pathkeeper.core.path_writer import PathWriter
    from pathkeeper.core.shadow import ShadowGroup
    from pathkeeper.models import (
        BackupRecord,
        DiagnosticReport,
        PathSnapshot,
        RuntimePathEntry,
    )

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Snapshot & adapter helpers
# ------------------------------------------------------------------


def get_snapshot_and_adapter() -> tuple[PathSnapshot, PathWriter, str]:
    """Return (snapshot, platform_adapter, os_name)."""
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    return snapshot, adapter, os_name


# ------------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------------


def read_current_report(scope: Scope) -> tuple[PathSnapshot, DiagnosticReport]:
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


def recent_backups(*, limit: int = 20) -> list[BackupRecord]:
    return list_backups(backups_home())[:limit]


def select_backup(
    identifier: str | None,
) -> tuple[BackupRecord, list[BackupRecord]]:
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


# ------------------------------------------------------------------
# Shadows
# ------------------------------------------------------------------


def find_shadows_report(scope: Scope) -> tuple[PathSnapshot, list[ShadowGroup]]:
    """Read the live PATH and return shadow groups."""
    from pathkeeper.core.shadow import find_shadows

    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    groups = find_shadows(
        system_entries=snapshot.system_path,
        user_entries=snapshot.user_path,
        os_name=normalized_os_name(),
        scope=scope,
    )
    return snapshot, groups


# ------------------------------------------------------------------
# Backup diff helpers
# ------------------------------------------------------------------


def diff_backup_vs_current(identifier: str, scope: Scope) -> tuple[str, str, str]:
    """Diff a backup against the current live PATH.

    Returns (backup_name, system_diff_text, user_diff_text).
    """
    from pathkeeper.core.diff import compute_diff, render_diff

    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    record, _ = select_backup(identifier)
    name = record.source_file.name if record.source_file else identifier
    sys_text = ""
    usr_text = ""
    if scope in {Scope.SYSTEM, Scope.ALL}:
        diff = compute_diff(record.system_path, snapshot.system_path, os_name)
        sys_text = render_diff(diff)
    if scope in {Scope.USER, Scope.ALL}:
        diff = compute_diff(record.user_path, snapshot.user_path, os_name)
        usr_text = render_diff(diff)
    return name, sys_text, usr_text


# ------------------------------------------------------------------
# Locate
# ------------------------------------------------------------------


def locate_executable_service(
    name: str, find_all: bool = False, drive: str | None = None
) -> list[Path]:
    """Search for an executable anywhere on the filesystem."""
    from pathkeeper.core.locate import locate_executable

    return locate_executable(name, find_all=find_all, drive=drive)


def detect_runtime_path_entries() -> list[RuntimePathEntry]:
    """Return the live PATH annotated with persisted vs runtime-only."""
    from pathkeeper.core.runtime_diff import detect_runtime_entries

    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    return detect_runtime_entries(snapshot, os_name)
