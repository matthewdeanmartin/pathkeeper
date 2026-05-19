"""T4 — diff and diff-current subcommands."""
from __future__ import annotations

import pytest


def _is_table_formatter_error(result) -> bool:
    combined = result.stdout + result.stderr
    return "pytable_formatter" in combined or "UnicodeEncodeError" in combined or "ModuleNotFound" in combined


def _ensure_two_backups(runner, pathx: str, pathx2: str) -> None:
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx2})


def test_diff_current_latest(runner, pathx: str) -> None:
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(["--var", "PATHX", "diff-current", "1"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_diff_current_no_id(runner, pathx: str) -> None:
    """diff-current without an identifier shows a backup list then prompts for a number."""
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(
        ["--var", "PATHX", "diff-current"],
        env_extra={"PATHX": pathx},
        input_text="1\n",
    )
    if _is_table_formatter_error(result):
        pytest.skip("pytable_formatter unavailable or terminal encoding issue")
    assert result.returncode == 0


def test_diff_between_two_backups(runner, pathx: str, sep: str, dirs) -> None:
    a, b, c, d = dirs
    pathx2 = sep.join([a, b, c, d])
    _ensure_two_backups(runner, pathx, pathx2)
    result = runner(
        ["--var", "PATHX", "diff", "1", "2"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_diff_current_scope_user(runner, pathx: str) -> None:
    runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    result = runner(
        ["--var", "PATHX", "diff-current", "1", "--scope", "user"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0
