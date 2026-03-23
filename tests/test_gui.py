"""Unit tests for the pathkeeper tkinter GUI.

Tests run with a real Tk root but never call mainloop().  We use
root.update() to process pending events and mock the core modules
so no real PATH is read or written.
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from typing import TYPE_CHECKING, Any
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

# Skip the entire module if tkinter is unavailable (headless CI, etc.)
tk = pytest.importorskip("tkinter")

if TYPE_CHECKING:
    import tkinter as _tk


from pathkeeper.models import (
    DiagnosticEntry,
    DiagnosticReport,
    DiagnosticSummary,
    PathSnapshot,
    BackupRecord,
    Scope,
)

# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def root() -> Generator[_tk.Tk, None, None]:
    """Create and destroy a Tk root for each test."""
    try:
        r = tk.Tk()
        r.withdraw()  # keep it invisible
    except tk.TclError:
        pytest.skip("No display available")
    yield r
    r.destroy()


def _fake_snapshot() -> PathSnapshot:
    return PathSnapshot(
        system_path=[r"C:\Windows\System32", r"C:\Windows"],
        user_path=[r"C:\Users\test\.local\bin", r"C:\Users\test\go\bin"],
        system_path_raw=r"C:\Windows\System32;C:\Windows",
        user_path_raw=r"C:\Users\test\.local\bin;C:\Users\test\go\bin",
    )


def _fake_report() -> DiagnosticReport:
    entries = [
        DiagnosticEntry(
            index=1,
            value=r"C:\Windows\System32",
            scope=Scope.SYSTEM,
            exists=True,
            is_dir=True,
            is_duplicate=False,
            duplicate_of=None,
            is_empty=False,
            has_unexpanded_vars=False,
            expanded_value=r"C:\Windows\System32",
        ),
        DiagnosticEntry(
            index=2,
            value=r"C:\Windows",
            scope=Scope.SYSTEM,
            exists=True,
            is_dir=True,
            is_duplicate=False,
            duplicate_of=None,
            is_empty=False,
            has_unexpanded_vars=False,
            expanded_value=r"C:\Windows",
        ),
        DiagnosticEntry(
            index=3,
            value=r"C:\missing",
            scope=Scope.USER,
            exists=False,
            is_dir=False,
            is_duplicate=False,
            duplicate_of=None,
            is_empty=False,
            has_unexpanded_vars=False,
            expanded_value=r"C:\missing",
        ),
    ]
    return DiagnosticReport(
        entries=entries,
        summary=DiagnosticSummary(
            total=3, valid=2, invalid=1, duplicates=0, empty=0, files=0
        ),
        os_name="windows",
        path_length=60,
    )


def _fake_backup(*, tag: str = "manual", note: str = "") -> BackupRecord:
    return BackupRecord(
        version=1,
        timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        hostname="testhost",
        os_name="windows",
        tag=tag,
        note=note,
        system_path=[r"C:\Windows\System32"],
        user_path=[r"C:\Users\test\.local\bin"],
        system_path_raw=r"C:\Windows\System32",
        user_path_raw=r"C:\Users\test\.local\bin",
        source_file=Path("2025-06-15T12-00-00_manual.json"),
    )


# ── helper tests ──────────────────────────────────────────────────


def test_entry_display_ok() -> None:
    from pathkeeper.gui.app import _entry_display

    entry = _fake_report().entries[0]  # valid
    tag, marker, notes = _entry_display(entry)
    assert tag == "ok"
    assert marker == "ok"
    assert notes == ""


def test_entry_display_missing() -> None:
    from pathkeeper.gui.app import _entry_display

    entry = _fake_report().entries[2]  # missing
    tag, marker, notes = _entry_display(entry)
    assert tag == "error"
    assert marker == "x"
    assert "missing" in notes


def test_entry_display_duplicate() -> None:
    from pathkeeper.gui.app import _entry_display

    entry = DiagnosticEntry(
        index=4,
        value=r"C:\Windows",
        scope=Scope.SYSTEM,
        exists=True,
        is_dir=True,
        is_duplicate=True,
        duplicate_of=2,
        is_empty=False,
        has_unexpanded_vars=False,
        expanded_value=r"C:\Windows",
    )
    tag, marker, notes = _entry_display(entry)
    assert tag == "warn"
    assert marker == "D"
    assert "#2" in notes


def test_entry_display_empty() -> None:
    from pathkeeper.gui.app import _entry_display

    entry = DiagnosticEntry(
        index=5,
        value="",
        scope=Scope.USER,
        exists=False,
        is_dir=False,
        is_duplicate=False,
        duplicate_of=None,
        is_empty=True,
        has_unexpanded_vars=False,
        expanded_value="",
    )
    tag, marker, notes = _entry_display(entry)
    assert tag == "dim"
    assert marker == "!"
    assert "empty" in notes


# ── widget tests ──────────────────────────────────────────────────


def test_make_tree(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import _make_tree

    parent = tk.Frame(root)
    tree = _make_tree(parent, [("a", "ColA", 100), ("b", "ColB", 200)])
    assert tree.cget("columns") == ("a", "b")


def test_make_output(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import _make_output, _output_set

    parent = tk.Frame(root)
    text = _make_output(parent, height=5)
    _output_set(text, "hello world")
    content = text.get("1.0", tk.END).strip()
    assert content == "hello world"


def test_make_scope_selector(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import _make_scope_selector

    parent = tk.Frame(root)
    var = _make_scope_selector(parent, default="user")
    assert var.get() == "user"
    var.set("system")
    assert var.get() == "system"


# ── panel instantiation tests ────────────────────────────────────


def _mock_services() -> dict[str, Any]:
    """Return a dict of patches that mock service calls for panel tests."""
    return {
        "read_current_report": patch(
            "pathkeeper.services.read_current_report",
            return_value=(_fake_snapshot(), _fake_report()),
        ),
        "recent_backups": patch(
            "pathkeeper.services.recent_backups",
            return_value=[_fake_backup()],
        ),
        "get_snapshot_and_adapter": patch(
            "pathkeeper.services.get_snapshot_and_adapter",
            return_value=(_fake_snapshot(), MagicMock(), "windows"),
        ),
    }


def test_dashboard_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import DashboardPanel, _BackgroundRunner

    patches = _mock_services()
    with patches["read_current_report"], patches["recent_backups"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = DashboardPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_inspect_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import InspectPanel, _BackgroundRunner

    patches = _mock_services()
    with patches["read_current_report"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = InspectPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_doctor_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import DoctorPanel, _BackgroundRunner

    patches = _mock_services()
    with patches["read_current_report"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = DoctorPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_backup_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import BackupPanel, _BackgroundRunner

    patches = _mock_services()
    with patches["recent_backups"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = BackupPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_edit_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import EditPanel, _BackgroundRunner

    patches = _mock_services()
    with patches["get_snapshot_and_adapter"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = EditPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_dedupe_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import DedupePanel, _BackgroundRunner

    runner = _BackgroundRunner(root)
    status = tk.StringVar()
    panel = DedupePanel(root, runner, status)
    root.update()
    assert panel.winfo_exists()


def test_schedule_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import SchedulePanel, _BackgroundRunner

    with patch("pathkeeper.core.schedule.schedule_status") as mock_status:
        mock_status.return_value = MagicMock(enabled=False, detail="")
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = SchedulePanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


# ── app tests ─────────────────────────────────────────────────────


def test_app_creates(root: _tk.Tk) -> None:
    """Verify PathkeeperApp can be instantiated (uses separate Toplevel)."""
    from pathkeeper.gui.app import PathkeeperApp, _CLR_BG  # noqa: F401

    patches = _mock_services()
    with patches["read_current_report"], patches["recent_backups"]:
        # PathkeeperApp is a Tk subclass; we can't create a second Tk, so
        # just test that our panel factory works with the existing root.
        from pathkeeper.gui.app import _build_panel, _BackgroundRunner

        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        parent = tk.Frame(root)
        panel = _build_panel("dashboard", parent, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_panel_factory_unknown_defaults_to_dashboard(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import _build_panel, _BackgroundRunner, DashboardPanel

    patches = _mock_services()
    with patches["read_current_report"], patches["recent_backups"]:
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        parent = tk.Frame(root)
        panel = _build_panel("nonexistent", parent, runner, status)
        assert isinstance(panel, DashboardPanel)


# ── background runner test ────────────────────────────────────────


def test_background_runner_creates(root: _tk.Tk) -> None:
    """Verify the runner can be instantiated."""
    from pathkeeper.gui.app import _BackgroundRunner

    runner = _BackgroundRunner(root)
    assert runner is not None


def test_background_runner_run_calls_func() -> None:
    """Test that the runner invokes the function in a thread."""
    import threading
    from unittest.mock import MagicMock

    mock_root = MagicMock()
    # Make after() just call the function directly (simulate main loop)
    mock_root.after = lambda _ms, fn, *a: fn(*a)

    from pathkeeper.gui.app import _BackgroundRunner

    runner = _BackgroundRunner(mock_root)
    results: list[int] = []

    def on_done(val: int) -> None:
        results.append(val)

    runner.run(lambda: 42, on_success=on_done)
    # Wait for the thread to finish
    import time

    deadline = time.monotonic() + 2.0
    while not results and time.monotonic() < deadline:
        time.sleep(0.01)
    assert results == [42]


def test_background_runner_error_calls_handler() -> None:
    """Test that errors are routed to the error handler."""
    from unittest.mock import MagicMock

    mock_root = MagicMock()
    mock_root.after = lambda _ms, fn, *a: fn(*a)

    from pathkeeper.gui.app import _BackgroundRunner

    runner = _BackgroundRunner(mock_root)
    errors: list[Exception] = []

    def on_err(exc: Exception) -> None:
        errors.append(exc)

    runner.run(lambda: 1 / 0, on_error=on_err)
    import time

    deadline = time.monotonic() + 2.0
    while not errors and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(errors) == 1
    assert isinstance(errors[0], ZeroDivisionError)


# ── services tests ────────────────────────────────────────────────


def test_services_format_timestamp() -> None:
    from pathkeeper.services import format_backup_timestamp_utc

    ts = datetime(2025, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    assert format_backup_timestamp_utc(ts) == "2025-03-15 14:30Z"
