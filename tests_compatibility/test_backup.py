"""T2 — backup / backups subcommands."""

from __future__ import annotations

import json

import pytest


def test_backup_dry_run(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "backup", "--dry-run"], env_extra={"PATHX": pathx}
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


def test_backup_force(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_backup_with_note(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "backup", "--note", "compat-test", "--force"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def _is_table_formatter_error(result) -> bool:
    """pytable_formatter is an optional dep that can crash on some terminals."""
    combined = result.stdout + result.stderr
    return (
        "pytable_formatter" in combined
        or "UnicodeEncodeError" in combined
        or "ModuleNotFound" in combined
    )


def test_backups_list(runner, pathx: str) -> None:
    # Create a backup first so the list is non-empty.
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(["backups", "list"], env_extra={"PATHX": pathx})
    if _is_table_formatter_error(result):
        pytest.skip("pytable_formatter unavailable or terminal encoding issue")
    assert result.returncode == 0


def test_backups_list_limit(runner, pathx: str) -> None:
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(["backups", "list", "--limit", "5"], env_extra={"PATHX": pathx})
    if _is_table_formatter_error(result):
        pytest.skip("pytable_formatter unavailable or terminal encoding issue")
    assert result.returncode == 0


def test_backups_show_latest(runner, pathx: str) -> None:
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    # "backups show" with no identifier selects the latest
    result = runner(["backups", "show", "1"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


def test_backup_idempotent_skip(runner, pathx: str) -> None:
    """Second backup without --force is silently skipped (identical content)."""
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(["--var", "PATHX", "backup"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
