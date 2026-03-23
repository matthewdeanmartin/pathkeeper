"""
Startup performance benchmarks for pathkeeper.

Measures wall time for the operations that run on every shell startup:
  - Module import (interpreter + Python import machinery)
  - `backup --quiet --tag auto` end-to-end in-process

Run manually:
    uv run python tests/bench_startup.py

Regression test (pytest):
    uv run pytest tests/bench_startup.py -v

The regression thresholds are intentionally loose (they must pass on a slow
CI machine) — their purpose is to catch catastrophic regressions (e.g. an
accidental eager import of a heavy library), not to enforce microsecond SLAs.
"""

from __future__ import annotations

import subprocess
import sys
import time
import timeit
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent


def _time(fn: "Callable[[], object]", *, repeat: int = 5) -> float:
    """Return median wall time in seconds over `repeat` calls."""
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    times.sort()
    return times[len(times) // 2]


# ---------------------------------------------------------------------------
# Benchmark: subprocess import time
# ---------------------------------------------------------------------------


def _measure_import_ms(repeat: int = 5) -> float:
    """
    Spawn a fresh Python process and measure the time from invocation to
    'import pathkeeper.cli' completing.  Returns median milliseconds.
    """
    snippet = "import pathkeeper.cli"
    cmd = [sys.executable, "-c", snippet]
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        subprocess.run(cmd, check=True, capture_output=True, cwd=str(_REPO_ROOT))
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2]


# ---------------------------------------------------------------------------
# Benchmark: in-process backup command
# ---------------------------------------------------------------------------


def _make_stub_adapter(tmp_path: Path) -> MagicMock:
    """Return a fake PathReader that satisfies read_snapshot()."""
    adapter = MagicMock()
    adapter.read_system_path.return_value = [r"C:\Windows\System32", r"C:\Windows"]
    adapter.read_user_path.return_value = [r"C:\Users\test\bin"]
    adapter.read_system_path_raw.return_value = r"C:\Windows\System32;C:\Windows"
    adapter.read_user_path_raw.return_value = r"C:\Users\test\bin"
    return adapter


def _measure_backup_ms(tmp_path: Path, repeat: int = 10) -> float:
    """
    Run the in-process backup logic (skipping the subprocess overhead) and
    return the median time in milliseconds over `repeat` iterations.

    The first iteration always creates a real backup file so that subsequent
    runs hit the fast "PATH unchanged — skip" path, which is what the shell
    startup hook hits 99% of the time.
    """
    from unittest.mock import patch

    from pathkeeper import cli
    from pathkeeper.config import AppConfig

    stub_adapter = _make_stub_adapter(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    def _run_backup() -> None:
        with (
            patch.object(cli, "load_config", return_value=AppConfig()),
            patch.object(cli, "get_platform_adapter", return_value=stub_adapter),
            patch.object(cli, "backups_home", return_value=backup_dir),
            patch.object(cli, "normalized_os_name", return_value="windows"),
        ):
            cli.run(["backup", "--quiet", "--tag", "auto"])

    # Warm-up: create the first backup so subsequent runs test the skip path.
    _run_backup()

    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        _run_backup()
        times.append((time.perf_counter() - t0) * 1000)
    times.sort()
    return times[len(times) // 2]


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------


def _run_benchmarks() -> None:
    import tempfile

    print("pathkeeper startup benchmarks")
    print("=" * 50)

    print("\n[1/2] Subprocess import time (fresh interpreter)...")
    import_ms = _measure_import_ms(repeat=5)
    print(f"      Median: {import_ms:.1f} ms")

    print("\n[2/2] In-process backup (skip path, already up-to-date)...")
    with tempfile.TemporaryDirectory() as td:
        backup_ms = _measure_backup_ms(Path(td), repeat=10)
    print(f"      Median: {backup_ms:.2f} ms")

    print()
    print("Summary")
    print("-" * 50)
    print(f"  Import:  {import_ms:.1f} ms   (threshold < 3000 ms)")
    print(f"  Backup:  {backup_ms:.2f} ms   (threshold < 50 ms)")


# ---------------------------------------------------------------------------
# Pytest regression tests
# ---------------------------------------------------------------------------

# Thresholds are intentionally generous to tolerate slow CI machines and
# cold filesystem caches.  Lower them if the baseline improves significantly.
_IMPORT_THRESHOLD_MS = 3000  # fresh subprocess import must finish under 3 s
_BACKUP_THRESHOLD_MS = 50  # in-process backup (skip path) under 50 ms


@pytest.mark.slow
def test_import_time_regression() -> None:
    """Module import must complete in under 3 seconds in a fresh interpreter."""
    ms = _measure_import_ms(repeat=3)
    assert ms < _IMPORT_THRESHOLD_MS, (
        f"Import took {ms:.1f} ms — exceeds {_IMPORT_THRESHOLD_MS} ms threshold. "
        "Check for accidental eager imports added to cli.py."
    )


@pytest.mark.slow
def test_backup_skip_path_regression(tmp_path: Path) -> None:
    """The backup 'already up-to-date' path must complete in under 50 ms."""
    ms = _measure_backup_ms(tmp_path, repeat=5)
    assert ms < _BACKUP_THRESHOLD_MS, (
        f"Backup (skip path) took {ms:.2f} ms — exceeds {_BACKUP_THRESHOLD_MS} ms threshold. "
        "Profile _backup_now() and check for slow I/O or unnecessary imports."
    )


if __name__ == "__main__":
    _run_benchmarks()
