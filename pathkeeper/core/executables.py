"""OS-aware helpers for listing executables inside a directory."""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404
from pathlib import Path
from subprocess import CalledProcessError  # nosec B404

# Extensions that are executable on Windows (checked case-insensitively)
_WIN_EXEC_EXTS: frozenset[str] = frozenset({".exe", ".cmd", ".bat", ".com", ".ps1"})

# Maximum number of names to collect before truncating (avoids huge lists for
# directories like /usr/bin that contain hundreds of tools).
_MAX_NAMES = 30


def list_executables(directory: str, os_name: str) -> list[str]:
    """Return sorted list of executable *names* (no path, no extension on Windows)
    found directly inside *directory*.

    Returns an empty list if the directory doesn't exist or can't be read.
    Truncates at ``_MAX_NAMES`` entries to keep output concise.
    """
    dirpath = Path(directory)
    if not dirpath.is_dir():
        return []
    names: list[str] = []
    try:
        entries = list(dirpath.iterdir())
    except OSError:
        return []

    if os_name == "windows":
        for entry in entries:
            if not entry.is_file():
                continue
            if entry.suffix.lower() in _WIN_EXEC_EXTS:
                # Strip the extension so "git.exe" → "git"
                names.append(entry.stem)
            if len(names) >= _MAX_NAMES:
                break
    else:
        for entry in entries:
            try:
                if entry.is_file() and os.access(str(entry), os.X_OK):
                    names.append(entry.name)
            except OSError:
                continue
            if len(names) >= _MAX_NAMES:
                break

    return sorted(set(names), key=str.casefold)


def _version_from_which(executable: str) -> tuple[int, ...] | None:
    """Try to determine the version of *executable* currently on PATH.

    Runs ``<executable> --version`` and parses the first dotted-number found.
    Returns None on any failure.
    """

    try:
        result = subprocess.run(  # nosec B603
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        output = result.stdout.strip() or result.stderr.strip()
        # Find first version-like token e.g. "3.14.0", "2.47.1"
        match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", output)
        if match:
            parts = tuple(int(g) for g in match.groups() if g is not None)
            return parts
    except (CalledProcessError, FileNotFoundError, OSError):
        return None
    return None
