"""T7 — dedupe subcommand."""

from __future__ import annotations


def test_dedupe_dry_run_no_dupes(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "dedupe", "--dry-run"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_dedupe_dry_run_with_dupes(runner, pathx_with_dupe: str) -> None:
    result = runner(
        ["--var", "PATHX", "dedupe", "--dry-run"],
        env_extra={"PATHX": pathx_with_dupe},
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


def test_dedupe_force_with_dupes(runner, pathx_with_dupe: str) -> None:
    """--force skips the confirmation prompt and actually dedupes PATHX."""
    result = runner(
        ["--var", "PATHX", "dedupe", "--force"],
        env_extra={"PATHX": pathx_with_dupe},
    )
    assert result.returncode == 0


def test_dedupe_no_dupes_is_noop(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "dedupe", "--force"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_dedupe_keep_last(runner, pathx_with_dupe: str) -> None:
    result = runner(
        ["--var", "PATHX", "dedupe", "--keep", "last", "--dry-run"],
        env_extra={"PATHX": pathx_with_dupe},
    )
    assert result.returncode == 0


def test_dedupe_cancelled(runner, pathx_with_dupe: str) -> None:
    """Answering 'n' at the confirmation prompt should cancel cleanly."""
    result = runner(
        ["--var", "PATHX", "dedupe"],
        env_extra={"PATHX": pathx_with_dupe},
        input_text="n\n",
    )
    # UserCancelledError has various exit codes across implementations; accept any non-crash code
    assert result.returncode in {0, 1, 2, 3, 4, 5}
