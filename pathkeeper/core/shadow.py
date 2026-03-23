"""Detect executable shadowing across PATH directories.

An executable is "shadowed" when the same name appears in more than one PATH
directory — only the first occurrence (highest priority) is actually invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pathkeeper.core.diagnostics import canonicalize_entry
from pathkeeper.core.executables import list_executables
from pathkeeper.models import Scope


@dataclass(frozen=True)
class ShadowEntry:
    """A single directory that provides a shadowed executable."""

    directory: str
    scope: Scope
    index: int  # 1-based display index


@dataclass(frozen=True)
class ShadowGroup:
    """One executable name that appears in multiple PATH directories."""

    name: str
    entries: list[ShadowEntry] = field(default_factory=list)

    @property
    def winner(self) -> ShadowEntry:
        return self.entries[0]

    @property
    def shadowed(self) -> list[ShadowEntry]:
        return self.entries[1:]


def find_shadows(
    *,
    system_entries: list[str],
    user_entries: list[str],
    os_name: str,
    scope: Scope,
) -> list[ShadowGroup]:
    """Return a list of shadow groups — executables found in multiple dirs.

    Only valid, non-duplicate directories are considered.  Results are sorted
    alphabetically by executable name.
    """
    # Build ordered list of (directory, scope, 1-based index)
    dirs: list[tuple[str, Scope, int]] = []
    seen_canonical: set[str] = set()
    idx = 1
    if scope in {Scope.SYSTEM, Scope.ALL}:
        for entry in system_entries:
            canon = canonicalize_entry(entry, os_name)
            if canon and canon not in seen_canonical:
                seen_canonical.add(canon)
                dirs.append((entry, Scope.SYSTEM, idx))
            idx += 1
    if scope in {Scope.USER, Scope.ALL}:
        for entry in user_entries:
            canon = canonicalize_entry(entry, os_name)
            if canon and canon not in seen_canonical:
                seen_canonical.add(canon)
                dirs.append((entry, Scope.USER, idx))
            idx += 1

    # Map executable name -> list of directories that contain it
    exe_map: dict[str, list[ShadowEntry]] = {}
    for directory, dir_scope, dir_index in dirs:
        names = list_executables(directory, os_name)
        for name in names:
            key = name.casefold() if os_name in {"windows", "darwin"} else name
            exe_map.setdefault(key, []).append(
                ShadowEntry(directory=directory, scope=dir_scope, index=dir_index)
            )

    # Keep only names with 2+ providers (i.e. shadows)
    groups = [
        ShadowGroup(name=key, entries=entries)
        for key, entries in sorted(exe_map.items())
        if len(entries) > 1
    ]
    return groups
