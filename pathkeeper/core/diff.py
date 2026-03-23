from __future__ import annotations

from pathkeeper.core.diagnostics import canonicalize_entry
from pathkeeper.models import PathDiff


def compute_diff(original: list[str], updated: list[str], os_name: str) -> PathDiff:
    original_keys = [canonicalize_entry(item, os_name) for item in original]
    updated_keys = [canonicalize_entry(item, os_name) for item in updated]
    added = [
        item
        for item, key in zip(updated, updated_keys, strict=True)
        if key not in original_keys
    ]
    removed = [
        item
        for item, key in zip(original, original_keys, strict=True)
        if key not in updated_keys
    ]
    reordered = [
        item
        for item, key in zip(updated, updated_keys, strict=True)
        if key in original_keys and original_keys.index(key) != updated_keys.index(key)
    ]
    return PathDiff(added=added, removed=removed, reordered=reordered)


def render_diff(diff: PathDiff) -> str:
    lines: list[str] = []
    if diff.added:
        lines.append("Added:")
        lines.extend(f"  + {entry}" for entry in diff.added)
    if diff.removed:
        lines.append("Removed:")
        lines.extend(f"  - {entry}" for entry in diff.removed)
    if diff.reordered:
        lines.append("Reordered:")
        lines.extend(f"  ~ {entry}" for entry in diff.reordered)
    return "\n".join(lines) if lines else "No changes."
