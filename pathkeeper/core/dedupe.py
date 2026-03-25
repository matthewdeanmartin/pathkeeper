from __future__ import annotations

from pathlib import Path

from pathkeeper.core.diagnostics import canonicalize_entry, expand_entry
from pathkeeper.models import CleanupResult


def _is_valid_directory(entry: str, os_name: str) -> bool:
    expanded = expand_entry(entry, os_name)
    return Path(expanded).is_dir()


def dedupe_entries(
    entries: list[str],
    os_name: str,
    *,
    keep: str = "first",
    remove_invalid: bool = True,
    pre_seen: set[str] | None = None,
) -> CleanupResult:
    if keep not in {"first", "last"}:
        raise ValueError("keep must be 'first' or 'last'")
    working = list(entries)
    if keep == "last":
        working.reverse()
    seen: set[str] = set(pre_seen) if pre_seen else set()
    kept: list[str] = []
    removed_duplicates: list[str] = []
    removed_invalid: list[str] = []
    removed_empty: list[str] = []
    for entry in working:
        if entry.strip() == "":
            removed_empty.append(entry)
            continue
        canonical = canonicalize_entry(entry, os_name)
        if canonical in seen:
            removed_duplicates.append(entry)
            continue
        if remove_invalid and not _is_valid_directory(entry, os_name):
            removed_invalid.append(entry)
            continue
        kept.append(entry)
        seen.add(canonical)
    if keep == "last":
        kept.reverse()
        removed_duplicates.reverse()
        removed_invalid.reverse()
        removed_empty.reverse()
    return CleanupResult(
        original=list(entries),
        cleaned=kept,
        removed_duplicates=removed_duplicates,
        removed_invalid=removed_invalid,
        removed_empty=removed_empty,
    )
