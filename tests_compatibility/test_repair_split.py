"""repair-truncated and split-long subcommand tests (dry-run only)."""
from __future__ import annotations

import platform


def test_repair_truncated_dry_run(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "repair-truncated", "--dry-run"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_repair_truncated_live_path_dry_run(runner) -> None:
    result = runner(["repair-truncated", "--dry-run"])
    assert result.returncode == 0


def test_split_long_dry_run(runner) -> None:
    """split-long is Windows-specific; on other platforms accept a graceful error."""
    result = runner(["split-long", "--dry-run"])
    if platform.system() == "Windows":
        assert result.returncode == 0
    else:
        # Non-Windows: may exit non-zero with an explanatory message
        combined = result.stdout + result.stderr
        assert combined.strip() != ""
