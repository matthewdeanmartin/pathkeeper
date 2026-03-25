from __future__ import annotations

import ntpath
import os
from pathlib import Path

from pathkeeper.core.diagnostics import expand_entry, has_unexpanded_variables
from pathkeeper.models import (
    BackupRecord,
    PathSnapshot,
    Scope,
    TruncatedPathCandidate,
    TruncatedPathRepair,
)


def _normalized_parts(value: str, os_name: str) -> list[str]:
    raw = value.strip().strip('"')
    if os_name == "windows":
        _drive, tail = ntpath.splitdrive(raw.replace("/", "\\"))
        return [part.casefold() for part in tail.split("\\") if part]
    parts = [part for part in raw.split("/") if part]
    if os_name == "darwin":
        return [part.casefold() for part in parts]
    return parts


def _path_matches_suffix(path: Path, target_parts: list[str], os_name: str) -> bool:
    candidate_parts = _normalized_parts(str(path), os_name)
    if len(candidate_parts) < len(target_parts):
        return False
    return candidate_parts[-len(target_parts) :] == target_parts


def _backup_candidates(
    *,
    records: list[BackupRecord],
    scope: Scope,
    target_parts: list[str],
    os_name: str,
) -> list[TruncatedPathCandidate]:
    candidates: list[TruncatedPathCandidate] = []
    seen: set[str] = set()
    for record in records:
        entries = record.system_path if scope is Scope.SYSTEM else record.user_path
        for entry in entries:
            candidate_path = Path(expand_entry(entry, os_name))
            candidate_text = str(candidate_path)
            canonical = (
                candidate_text.casefold()
                if os_name in {"windows", "darwin"}
                else candidate_text
            )
            if canonical in seen or not candidate_path.is_dir():
                continue
            if not _path_matches_suffix(candidate_path, target_parts, os_name):
                continue
            candidates.append(
                TruncatedPathCandidate(
                    path=candidate_text,
                    source=f"backup {_format_backup_source(record)}",
                )
            )
            seen.add(canonical)
    return candidates


def _filesystem_candidates(
    *,
    search_roots: list[Path],
    target_parts: list[str],
    os_name: str,
    limit: int,
    existing: set[str],
) -> list[TruncatedPathCandidate]:
    candidates: list[TruncatedPathCandidate] = []
    target_leaf = target_parts[-1]
    for root in search_roots:
        if not root.exists() or not root.is_dir():
            continue
        for current_dir, _dirnames, _filenames in os.walk(
            root, onerror=lambda _error: None
        ):
            current_path = Path(current_dir)
            current_name = (
                current_path.name.casefold()
                if os_name in {"windows", "darwin"}
                else current_path.name
            )
            if current_name != target_leaf:
                continue
            if not _path_matches_suffix(current_path, target_parts, os_name):
                continue
            candidate_text = str(current_path)
            canonical = (
                candidate_text.casefold()
                if os_name in {"windows", "darwin"}
                else candidate_text
            )
            if canonical in existing:
                continue
            candidates.append(
                TruncatedPathCandidate(path=candidate_text, source=f"disk {root}")
            )
            existing.add(canonical)
            if len(candidates) >= limit:
                return candidates
    return candidates


def default_search_roots(os_name: str) -> list[Path]:
    roots: list[Path] = []
    if os_name == "windows":
        for variable in (
            "LOCALAPPDATA",
            "APPDATA",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "USERPROFILE",
            "SystemDrive",
        ):
            value = os.environ.get(variable)
            if value:
                roots.append(Path(value))
        home = Path.home()
        roots.append(home)
        if home.anchor:
            roots.append(Path(home.anchor))
    else:
        roots.extend([Path.home(), Path("/usr/local"), Path("/usr"), Path("/opt")])
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        canonical = (
            str(root).casefold() if os_name in {"windows", "darwin"} else str(root)
        )
        if canonical in seen:
            continue
        seen.add(canonical)
        unique.append(root)
    return unique


def _format_backup_source(record: BackupRecord) -> str:
    if record.source_file is not None:
        return record.source_file.name
    return record.timestamp.isoformat()


def _find_scope_repairs(
    *,
    entries: list[str],
    scope: Scope,
    display_start: int,
    os_name: str,
    records: list[BackupRecord],
    search_roots: list[Path],
    max_candidates: int,
) -> list[TruncatedPathRepair]:
    repairs: list[TruncatedPathRepair] = []
    for index, entry in enumerate(entries):
        expanded_text = expand_entry(entry, os_name)
        if entry.strip() == "" or has_unexpanded_variables(expanded_text, os_name):
            continue
        expanded = Path(expanded_text)
        if expanded.exists():
            continue
        target_parts = _normalized_parts(entry, os_name)
        if len(target_parts) < 2:
            continue
        backup_candidates = _backup_candidates(
            records=records, scope=scope, target_parts=target_parts, os_name=os_name
        )
        seen = {
            (
                candidate.path.casefold()
                if os_name in {"windows", "darwin"}
                else candidate.path
            )
            for candidate in backup_candidates
        }
        disk_candidates: list[TruncatedPathCandidate] = []
        if not backup_candidates:
            disk_candidates = _filesystem_candidates(
                search_roots=search_roots,
                target_parts=target_parts,
                os_name=os_name,
                limit=max_candidates,
                existing=seen,
            )
        candidates = [*backup_candidates, *disk_candidates]
        if not candidates:
            continue
        repairs.append(
            TruncatedPathRepair(
                display_index=display_start + index,
                scope_index=index,
                scope=scope,
                value=entry,
                candidates=candidates,
            )
        )
    return repairs


def find_truncated_repairs(
    *,
    snapshot: PathSnapshot,
    scope: Scope,
    os_name: str,
    records: list[BackupRecord],
    search_roots: list[Path] | None = None,
    max_candidates: int = 5,
) -> list[TruncatedPathRepair]:
    roots = (
        list(search_roots)
        if search_roots is not None
        else default_search_roots(os_name)
    )
    repairs: list[TruncatedPathRepair] = []
    display_start = 1
    if scope in {Scope.SYSTEM, Scope.ALL}:
        repairs.extend(
            _find_scope_repairs(
                entries=snapshot.system_path,
                scope=Scope.SYSTEM,
                display_start=display_start,
                os_name=os_name,
                records=records,
                search_roots=roots,
                max_candidates=max_candidates,
            )
        )
        display_start += len(snapshot.system_path)
    if scope in {Scope.USER, Scope.ALL}:
        repairs.extend(
            _find_scope_repairs(
                entries=snapshot.user_path,
                scope=Scope.USER,
                display_start=display_start,
                os_name=os_name,
                records=records,
                search_roots=roots,
                max_candidates=max_candidates,
            )
        )
    return repairs
