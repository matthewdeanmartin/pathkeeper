from __future__ import annotations

import logging
import os
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path

from pathkeeper.config import load_config
from pathkeeper.core.populate import _expand_pattern, load_catalog
from pathkeeper.platform import normalized_os_name

logger = logging.getLogger(__name__)

_WIN_EXEC_EXTS = (".exe", ".cmd", ".bat", ".com", ".ps1")


def _get_search_extensions(os_name: str) -> tuple[str, ...]:
    if os_name == "windows":
        return _WIN_EXEC_EXTS
    return ("",)


def _is_executable(path: Path, os_name: str) -> bool:
    if not path.is_file():
        return False
    if os_name == "windows":
        return path.suffix.lower() in _WIN_EXEC_EXTS
    return os.access(path, os.X_OK)


def _find_with_rg(name: str, root: str, find_all: bool) -> list[Path]:
    """Search for filename using ripgrep."""
    cmd = ["rg", "--files", "--glob", f"*{name}*", root]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and not result.stdout:
            return []

        paths = []
        for line in result.stdout.splitlines():
            path = Path(line)
            if path.name.lower().startswith(name.lower()):
                paths.append(path)
                if not find_all:
                    return paths
        return paths
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_fd(name: str, root: str, find_all: bool, os_name: str) -> list[Path]:
    """Search for filename using fd-find."""
    cmd = ["fd", "-t", "x" if os_name != "windows" else "f", "-I", name, root]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 and not result.stdout:
            return []

        paths = []
        for line in result.stdout.splitlines():
            path = Path(line)
            paths.append(path)
            if not find_all:
                return paths
        return paths
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_ag(name: str, root: str, find_all: bool) -> list[Path]:
    """Search using the silver searcher (ag)."""
    cmd = ["ag", "-g", name, root]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0 and not result.stdout:
            return []
        paths = [Path(p) for p in result.stdout.splitlines()]
        return paths if find_all else paths[:1]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_mdfind(name: str, find_all: bool) -> list[Path]:
    """Search using macOS Spotlight (mdfind)."""
    cmd = ["mdfind", "-name", name]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        paths = [Path(p) for p in result.stdout.splitlines() if p.endswith(name)]
        return paths if find_all else paths[:1]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_locate(name: str, find_all: bool) -> list[Path]:
    """Search using locate (database-backed)."""
    cmd = ["locate", "-b", f"\\{name}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        paths = [Path(p) for p in result.stdout.splitlines()]
        return paths if find_all else paths[:1]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_find_cmd(name: str, root: str, find_all: bool) -> list[Path]:
    """Search using the standard Unix find command."""
    cmd = ["find", root, "-name", name, "-executable", "-type", "f"]
    if not find_all:
        cmd.extend(["-print", "-quit"])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            return []
        return [Path(p) for p in result.stdout.splitlines()]
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_win_dir(name: str, root: str, find_all: bool) -> list[Path]:
    """Search using Windows native dir command."""
    search_pattern = os.path.join(root, f"{name}*")
    cmd = ["cmd", "/c", "dir", "/s", "/b", search_pattern]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            return []
        paths = []
        exts = _get_search_extensions("windows")
        for line in result.stdout.splitlines():
            p = Path(line)
            if p.name.lower() == name.lower() or any(
                p.name.lower() == (name + e).lower() for e in exts
            ):
                paths.append(p)
                if not find_all:
                    return paths
        return paths
    except (subprocess.SubprocessError, FileNotFoundError):
        return []


def _find_with_python(name: str, root: str, find_all: bool, os_name: str) -> list[Path]:
    """Fallback search using os.walk with error suppression."""
    found = []
    exts = _get_search_extensions(os_name)
    name_lower = name.lower()

    def on_error(_: OSError) -> None:
        pass

    for dirpath, _dirnames, filenames in os.walk(root, onerror=on_error):
        for filename in filenames:
            fn_lower = filename.lower()
            match = False
            if os_name == "windows":
                if fn_lower == name_lower:
                    match = True
                else:
                    for ext in exts:
                        if fn_lower == name_lower + ext:
                            match = True
                            break
            else:
                if fn_lower == name_lower:
                    match = True

            if match:
                path = Path(dirpath) / filename
                try:
                    if _is_executable(path, os_name):
                        found.append(path)
                        if not find_all:
                            return found
                except (OSError, PermissionError):
                    continue

    return found


def locate_executable(
    name: str,
    find_all: bool = False,
    drive: str | None = None,
    os_name: str | None = None,
) -> list[Path]:
    if os_name is None:
        os_name = normalized_os_name()

    config = load_config()
    catalog = load_catalog(config)

    found: list[Path] = []
    seen: set[Path] = set()

    def add_found(paths: Iterable[Path]) -> None:
        for p in paths:
            try:
                if not p.exists():
                    continue
                resolved = p.resolve()
                if resolved not in seen:
                    found.append(resolved)
                    seen.add(resolved)
            except (OSError, PermissionError):
                if p not in seen:
                    found.append(p)
                    seen.add(p)

    # 1. Likely locations first
    likely_roots = []
    for tool in catalog:
        match = (name.lower() == tool.name.lower()) or (
            name.lower() in [e.lower() for e in tool.executables]
        )

        if match:
            import glob

            for pattern in tool.patterns:
                expanded = _expand_pattern(pattern)
                likely_roots.extend(glob.glob(expanded))

    for path_str in os.environ.get("PATH", "").split(os.pathsep):
        if path_str:
            likely_roots.append(path_str)

    for root_str in dict.fromkeys(likely_roots):
        try:
            root = Path(root_str)
            if not root.is_dir():
                continue

            exts = _get_search_extensions(os_name)
            for ext in exts:
                p = root / (name + ext)
                if _is_executable(p, os_name):
                    add_found([p])
                    if not find_all:
                        return found
        except (OSError, PermissionError):
            continue

    # 2. Deep search cascade
    search_root = drive if drive else ("C:\\" if os_name == "windows" else "/")

    # OS-Specific fast tools
    if os_name == "macos":
        add_found(_find_with_mdfind(name, find_all))
        if found and not find_all:
            return found

    # Cross-platform fast tools
    if shutil.which("rg"):
        add_found(_find_with_rg(name, search_root, find_all))
        if found and not find_all:
            return found

    if shutil.which("fd"):
        add_found(_find_with_fd(name, search_root, find_all, os_name))
        if found and not find_all:
            return found

    if shutil.which("ag"):
        add_found(_find_with_ag(name, search_root, find_all))
        if found and not find_all:
            return found

    # OS-Specific standard tools
    if os_name != "windows":
        if shutil.which("locate"):
            add_found(_find_with_locate(name, find_all))
            if found and not find_all:
                return found

        if shutil.which("find"):
            add_found(_find_with_find_cmd(name, search_root, find_all))
            if found and not find_all:
                return found
    else:
        add_found(_find_with_win_dir(name, search_root, find_all))
        if found and not find_all:
            return found

    # Fallback to python
    add_found(_find_with_python(name, search_root, find_all, os_name))

    return found
