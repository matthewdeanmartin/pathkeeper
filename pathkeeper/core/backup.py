from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from pathlib import Path

from pathkeeper.config import AppConfig
from pathkeeper.errors import BackupNotFoundError
from pathkeeper.models import BackupRecord, PathSnapshot


BACKUP_VERSION = 1


def backup_filename(timestamp: datetime, tag: str) -> str:
    return f"{timestamp.strftime('%Y-%m-%dT%H-%M-%S')}_{tag}.json"


def create_backup(
    snapshot: PathSnapshot,
    *,
    backup_dir: Path,
    os_name: str,
    tag: str,
    note: str,
) -> Path:
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
    destination = backup_dir / backup_filename(timestamp, tag)
    suffix = 1
    while destination.exists():
        destination = backup_dir / f"{destination.stem}-{suffix:02d}.json"
        suffix += 1
    destination.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    return destination


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


def list_backups(backup_dir: Path) -> list[BackupRecord]:
    if not backup_dir.exists():
        return []
    records = [load_backup(path) for path in backup_dir.glob("*.json")]
    return sorted(records, key=lambda item: item.timestamp, reverse=True)


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


def prune_backups(backup_dir: Path, config: AppConfig) -> None:
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
    for record in records:
        if record.source_file is not None and record.source_file not in keep:
            record.source_file.unlink(missing_ok=True)

