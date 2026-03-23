from __future__ import annotations

import hashlib
import json
import logging
import socket
from datetime import UTC, datetime
from pathlib import Path

from pathkeeper.config import AppConfig
from pathkeeper.errors import BackupNotFoundError
from pathkeeper.models import BackupRecord, PathSnapshot


BACKUP_VERSION = 1
logger = logging.getLogger(__name__)


def backup_filename(timestamp: datetime, tag: str) -> str:
    return f"{timestamp.strftime('%Y-%m-%dT%H-%M-%S')}_{tag}.json"


def _load_latest_backup(backup_dir: Path) -> BackupRecord | None:
    """Load only the most recent backup file without reading the rest."""
    paths = _sorted_backup_paths(backup_dir)
    if not paths:
        return None
    return load_backup(paths[0])


def create_backup(
    snapshot: PathSnapshot,
    *,
    backup_dir: Path,
    os_name: str,
    tag: str,
    note: str,
    force: bool = False,
) -> tuple[Path | None, list[BackupRecord] | None]:
    """Create a backup and return (destination_path, loaded_records).

    loaded_records is the full sorted backup list when it was needed for
    pruning (i.e. a new backup was written); None when skipped.  Callers
    can pass it straight to prune_backups() to avoid re-reading the dir.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC)
    record = BackupRecord(
        version=BACKUP_VERSION,
        timestamp=timestamp,
        hostname=socket.gethostname(),
        os_name=os_name,
        tag=tag,
        note=note,
        system_path=list(snapshot.system_path),
        user_path=list(snapshot.user_path),
        system_path_raw=snapshot.system_path_raw,
        user_path_raw=snapshot.user_path_raw,
    )
    latest = _load_latest_backup(backup_dir)
    if not force and latest is not None and latest.snapshot == snapshot and latest.os_name == os_name:
        logger.warning("Skipping backup because the current PATH matches the latest saved backup.")
        return None, None
    logger.info("Creating %s backup in %s", tag, backup_dir)
    destination = backup_dir / backup_filename(timestamp, tag)
    suffix = 1
    while destination.exists():
        destination = backup_dir / f"{destination.stem}-{suffix:02d}.json"
        suffix += 1
    destination.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    logger.info("Created backup at %s", destination)
    # Re-read the full list now that we've written the new file (needed for pruning).
    all_records = list_backups(backup_dir)
    return destination, all_records


def load_backup(path: Path) -> BackupRecord:
    payload = json.loads(path.read_text(encoding="utf-8"))
    timestamp = datetime.fromisoformat(str(payload["timestamp"]).replace("Z", "+00:00"))
    return BackupRecord(
        version=int(payload["version"]),
        timestamp=timestamp,
        hostname=str(payload["hostname"]),
        os_name=str(payload["os"]),
        tag=str(payload["tag"]),
        note=str(payload["note"]),
        system_path=[str(item) for item in payload["system_path"]],
        user_path=[str(item) for item in payload["user_path"]],
        system_path_raw=str(payload["system_path_raw"]),
        user_path_raw=str(payload["user_path_raw"]),
        source_file=path,
    )


def backup_content_hash(record: BackupRecord) -> str:
    payload = {
        "os": record.os_name,
        "system_path": record.system_path,
        "user_path": record.user_path,
        "system_path_raw": record.system_path_raw,
        "user_path_raw": record.user_path_raw,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return digest[:12]


def _sorted_backup_paths(backup_dir: Path) -> list[Path]:
    """Return backup JSON paths sorted newest-first by filename (ISO timestamp prefix)."""
    return sorted(backup_dir.glob("*.json"), key=lambda p: p.name, reverse=True)


def list_backups(backup_dir: Path) -> list[BackupRecord]:
    if not backup_dir.exists():
        return []
    return [load_backup(path) for path in _sorted_backup_paths(backup_dir)]


def resolve_backup(identifier: str, backup_dir: Path) -> BackupRecord:
    candidate = Path(identifier).expanduser()
    if candidate.exists():
        return load_backup(candidate)
    for record in list_backups(backup_dir):
        if record.source_file is None:
            continue
        if record.source_file.name == identifier or record.source_file.stem.startswith(identifier):
            return record
    raise BackupNotFoundError(f"Backup not found: {identifier}")


def prune_backups(backup_dir: Path, config: AppConfig, records: list[BackupRecord] | None = None) -> None:
    if records is None:
        records = list_backups(backup_dir)
    auto_records = [record for record in records if record.tag == "auto"]
    manual_records = [record for record in records if record.tag == "manual"]
    keep: set[Path] = set()
    keep.update(
        record.source_file
        for record in auto_records[: config.general.max_auto_backups]
        if record.source_file is not None
    )
    keep.update(
        record.source_file
        for record in manual_records[: config.general.max_manual_backups]
        if record.source_file is not None
    )
    remaining = [record for record in records if record.source_file not in keep]
    keep.update(
        record.source_file
        for record in remaining[: max(0, config.general.max_backups - len(keep))]
        if record.source_file is not None
    )
    removed = 0
    for record in records:
        if record.source_file is not None and record.source_file not in keep:
            record.source_file.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info("Pruned %s old backup(s).", removed)

