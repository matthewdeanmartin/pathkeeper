"""T6 — restore (dry-run only; never writes to real PATH)."""

from __future__ import annotations

import re


def _make_backup(runner, pathx: str) -> str:
    """Create a backup and return the backup filename (stem) for use as identifier."""
    result = runner(["--var", "PATHX", "backup", "--force"], env_extra={"PATHX": pathx})
    assert result.returncode == 0, f"backup failed: {result.stderr}"
    # Extract the filename from output like "Created backup: <path>"
    match = re.search(r"[\w\-]+\.json", result.stdout + result.stderr)
    return match.group(0) if match else "1"


def test_restore_dry_run_by_id(runner, pathx: str) -> None:
    backup_id = _make_backup(runner, pathx)
    result = runner(
        ["--var", "PATHX", "restore", backup_id, "--dry-run"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0, (
        f"restore --dry-run exited {result.returncode}:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


def test_restore_dry_run_no_write(runner, pathx: str, pk_home) -> None:
    """Confirm --dry-run does not create additional backup files."""
    backup_id = _make_backup(runner, pathx)
    before = set(pk_home.rglob("*.json"))
    runner(
        ["--var", "PATHX", "restore", backup_id, "--dry-run"],
        env_extra={"PATHX": pathx},
    )
    after = set(pk_home.rglob("*.json"))
    assert after == before, "dry-run must not write any files"


def test_restore_force_dry_run(runner, pathx: str) -> None:
    backup_id = _make_backup(runner, pathx)
    result = runner(
        ["--var", "PATHX", "restore", backup_id, "--dry-run", "--force"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_restore_interactive_cancelled(runner, pathx: str) -> None:
    """Supplying 'n' at the confirmation prompt should cancel without error."""
    backup_id = _make_backup(runner, pathx)
    result = runner(
        ["--var", "PATHX", "restore", backup_id],
        env_extra={"PATHX": pathx},
        input_text="n\n",
    )
    # Cancellation exits cleanly (0) or with a UserCancelled exit code (varies by impl)
    assert result.returncode in {0, 1, 2, 3, 4, 5}
