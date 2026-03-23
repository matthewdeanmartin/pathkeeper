"""Detect PATH entries injected at runtime (not persisted in registry / rc files).

Compares the live process PATH (``os.environ["PATH"]``) against the persisted
system + user PATH read from the registry (Windows) or rc files (Unix).
Entries present in the live PATH but absent from the persisted PATH were added
at runtime — e.g. by a parent shell, IDE, or manual ``PATH=…`` invocation.
"""

from __future__ import annotations

import os

from pathkeeper.core.diagnostics import canonicalize_entry
from pathkeeper.models import PathSnapshot, RuntimePathEntry, Scope


def detect_runtime_entries(
    snapshot: PathSnapshot,
    os_name: str,
) -> list[RuntimePathEntry]:
    """Compare live ``$PATH`` against the persisted snapshot.

    Returns every entry in the live PATH annotated with whether it also
    appears in the persisted PATH.  Entries not found in the persisted
    snapshot are marked ``persisted=False``.
    """
    # Build canonical set of persisted entries
    persisted_system = {
        canonicalize_entry(e, os_name) for e in snapshot.system_path if e.strip()
    }
    persisted_user = {
        canonicalize_entry(e, os_name) for e in snapshot.user_path if e.strip()
    }
    persisted_all = persisted_system | persisted_user

    # Read the live process PATH
    sep = ";" if os_name == "windows" else ":"
    live_entries = os.environ.get("PATH", "").split(sep)

    results: list[RuntimePathEntry] = []
    for entry in live_entries:
        if not entry.strip():
            continue
        canon = canonicalize_entry(entry, os_name)
        if canon in persisted_system:
            results.append(
                RuntimePathEntry(value=entry, persisted=True, scope=Scope.SYSTEM)
            )
        elif canon in persisted_user:
            results.append(
                RuntimePathEntry(value=entry, persisted=True, scope=Scope.USER)
            )
        elif canon in persisted_all:
            results.append(RuntimePathEntry(value=entry, persisted=True, scope=None))
        else:
            results.append(RuntimePathEntry(value=entry, persisted=False, scope=None))

    return results
