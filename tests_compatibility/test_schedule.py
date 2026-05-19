"""schedule subcommand tests (status and dry-run only)."""
from __future__ import annotations


def test_schedule_status(runner) -> None:
    result = runner(["schedule", "status"])
    # schedule status reads state; exit 0 whether enabled or not
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


def test_schedule_install_dry_run(runner) -> None:
    result = runner(["schedule", "install", "--dry-run"])
    assert result.returncode == 0


def test_schedule_remove_dry_run(runner) -> None:
    result = runner(["schedule", "remove", "--dry-run"])
    assert result.returncode == 0
