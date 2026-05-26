"""locate subcommand tests.

The `locate` command does a full disk scan as a fallback. Non-trivial searches
are marked @pytest.mark.slow and excluded from the default test run.  Only the
fast "found in PATH" case runs by default.
"""

from __future__ import annotations

import platform

import pytest


def _windows() -> bool:
    return platform.system() == "Windows"


def test_locate_known(runner) -> None:
    """Locate an executable that is on PATH — fast, no disk scan triggered."""
    exe = "cmd" if _windows() else "sh"
    result = runner(["locate", exe])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


@pytest.mark.slow
def test_locate_missing(runner) -> None:
    """Confirm exit code != 0 for a nonexistent exe — triggers full disk scan."""
    if _windows():
        result = runner(
            [
                "locate",
                "__no_such_exe_pathkeeper_compat_test__",
                "--drive",
                "C:\\Windows",
            ],
            timeout=300,
        )
    else:
        result = runner(
            ["locate", "__no_such_exe_pathkeeper_compat_test__"], timeout=300
        )
    assert result.returncode != 0


@pytest.mark.slow
def test_locate_all(runner) -> None:
    """--all triggers a full disk scan — only run with -m slow."""
    exe = "cmd" if _windows() else "sh"
    result = runner(["locate", exe, "--all"], timeout=300)
    assert result.returncode == 0
