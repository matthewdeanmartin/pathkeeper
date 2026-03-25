"""Unit tests for the pathkeeper tkinter GUI.

Tests run with a real Tk root but never call mainloop().  We use
root.update() to process pending events and mock the core modules
so no real PATH is read or written.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from pathkeeper.models import (
    BackupRecord,
    DiagnosticEntry,
    DiagnosticReport,
    DiagnosticSummary,
    PathSnapshot,
    Scope,
)

# Skip the entire module if tkinter is unavailable (headless CI, etc.)
tk = pytest.importorskip("tkinter")

if TYPE_CHECKING:
    import tkinter as _tk

# ── fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def root() -> Generator[_tk.Tk]:
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
        timestamp=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
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


def test_split_long_panel_creates(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import SplitLongPanel, _BackgroundRunner

    class _EnvAdapter:
        def read_user_environment(self) -> dict[str, str]:
            return {}

    with patch(
        "pathkeeper.services.get_snapshot_and_adapter",
        return_value=(_fake_snapshot(), _EnvAdapter(), "windows"),
    ):
        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        panel = SplitLongPanel(root, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_schedule_panel_install_falls_back_to_logon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathkeeper import platform as platform_mod
    from pathkeeper.core import schedule
    from pathkeeper.errors import PermissionDeniedError
    from pathkeeper.gui.app import SchedulePanel

    calls: list[str] = []

    def fake_install(_os_name: str, _interval: str, *, trigger: str = "startup") -> str:
        calls.append(trigger)
        if trigger == "startup":
            raise PermissionDeniedError("Access is denied.")
        return "Installed Windows scheduled task for user logon."

    monkeypatch.setattr(schedule, "install_schedule", fake_install)
    monkeypatch.setattr(platform_mod, "normalized_os_name", lambda: "windows")

    result = SchedulePanel._do_install()

    assert calls == ["startup", "logon"]
    assert "per-user logon task instead" in result
    assert "Installed Windows scheduled task for user logon." in result


def test_split_long_panel_apply_reports_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathkeeper.gui.app import SplitLongPanel

    snapshot = PathSnapshot(
        system_path=[],
        user_path=[
            r"C:\Tools\Alpha\bin",
            r"C:\Tools\Beta\bin",
            r"C:\Tools\Gamma\bin",
            r"C:\Tools\Delta\bin",
        ],
        system_path_raw="",
        user_path_raw=(
            r"C:\Tools\Alpha\bin;C:\Tools\Beta\bin;C:\Tools\Gamma\bin;C:\Tools\Delta\bin"
        ),
    )

    class _Adapter:
        def __init__(self) -> None:
            self.user = list(snapshot.user_path)
            self.user_env: dict[str, str] = {}
            self.system_env: dict[str, str] = {}

        def read_user_environment(self) -> dict[str, str]:
            return dict(self.user_env)

        def read_system_environment(self) -> dict[str, str]:
            return dict(self.system_env)

        def write_user_path(self, entries: list[str]) -> None:
            self.user = list(entries)

        def write_user_env_var(self, name: str, value: str) -> None:
            self.user_env[name] = value

        def write_system_env_var(self, name: str, value: str) -> None:
            self.system_env[name] = value

        def delete_user_env_var(self, name: str) -> None:
            self.user_env.pop(name, None)

        def delete_system_env_var(self, name: str) -> None:
            self.system_env.pop(name, None)

    adapter = _Adapter()
    monkeypatch.setattr(
        "pathkeeper.services.get_snapshot_and_adapter",
        lambda: (snapshot, adapter, "windows"),
    )
    monkeypatch.setattr("pathkeeper.services.backup_now", lambda **_kwargs: None)

    text = SplitLongPanel._do_apply("user", 40, 32, "DEV_PATHS")

    assert "Split-long complete." in text
    assert adapter.user == ["%DEV_PATHS_1%"]
    assert set(adapter.user_env) == {"DEV_PATHS_1"}


def test_schedule_panel_refreshes_status_after_install(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import SchedulePanel

    runner = MagicMock()
    status = tk.StringVar()
    panel = SchedulePanel(root, runner, status)
    runner.reset_mock()

    panel._on_install_success("Installed Windows scheduled task.")

    runner.run.assert_called_once_with(
        panel._fetch_status, on_success=panel._display, on_error=panel._on_error
    )
    assert status.get() == "Schedule installed; refreshing status..."


def test_launch_gui_logs_lifecycle(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from pathkeeper.gui import app as gui_app

    mock_app = MagicMock()
    monkeypatch.setattr(gui_app, "PathkeeperApp", MagicMock(return_value=mock_app))

    with caplog.at_level(logging.INFO):
        result = gui_app.launch_gui()

    assert result == 0
    assert "Launching pathkeeper GUI." in caplog.text
    assert "Pathkeeper GUI exited." in caplog.text


# ── app tests ─────────────────────────────────────────────────────


def test_app_creates(root: _tk.Tk) -> None:
    """Verify PathkeeperApp can be instantiated (uses separate Toplevel)."""
    from pathkeeper.gui.app import _CLR_BG, PathkeeperApp  # noqa: F401

    patches = _mock_services()
    with patches["read_current_report"], patches["recent_backups"]:
        # PathkeeperApp is a Tk subclass; we can't create a second Tk, so
        # just test that our panel factory works with the existing root.
        from pathkeeper.gui.app import _BackgroundRunner, _build_panel

        runner = _BackgroundRunner(root)
        status = tk.StringVar()
        parent = tk.Frame(root)
        panel = _build_panel("dashboard", parent, runner, status)
        root.update()
        assert panel.winfo_exists()


def test_panel_factory_unknown_defaults_to_dashboard(root: _tk.Tk) -> None:
    from pathkeeper.gui.app import DashboardPanel, _BackgroundRunner, _build_panel

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
    import time
    from unittest.mock import MagicMock

    mock_root = MagicMock()
    pending: list[tuple[object, tuple[object, ...]]] = []

    def fake_after(_ms: int, fn: object, *args: object) -> None:
        pending.append((fn, args))

    mock_root.after = fake_after

    from pathkeeper.gui.app import _BackgroundRunner

    runner = _BackgroundRunner(mock_root)
    results: list[int] = []

    def on_done(val: int) -> None:
        results.append(val)

    runner.run(lambda: 42, on_success=on_done)
    deadline = time.monotonic() + 2.0
    while not results and time.monotonic() < deadline:
        while pending:
            fn, args = pending.pop(0)
            fn(*args)  # type: ignore[operator]
        time.sleep(0.01)
    assert results == [42]


def test_background_runner_error_calls_handler() -> None:
    """Test that errors are routed to the error handler."""
    import time
    from unittest.mock import MagicMock

    mock_root = MagicMock()
    pending: list[tuple[object, tuple[object, ...]]] = []

    def fake_after(_ms: int, fn: object, *args: object) -> None:
        pending.append((fn, args))

    mock_root.after = fake_after

    from pathkeeper.gui.app import _BackgroundRunner

    runner = _BackgroundRunner(mock_root)
    errors: list[Exception] = []

    def on_err(exc: Exception) -> None:
        errors.append(exc)

    runner.run(lambda: 1 / 0, on_error=on_err)
    deadline = time.monotonic() + 2.0
    while not errors and time.monotonic() < deadline:
        while pending:
            fn, args = pending.pop(0)
            fn(*args)  # type: ignore[operator]
        time.sleep(0.01)
    assert len(errors) == 1
    assert isinstance(errors[0], ZeroDivisionError)


def test_background_runner_skips_destroyed_widget_callback(
    root: _tk.Tk, caplog: pytest.LogCaptureFixture
) -> None:
    from pathkeeper.gui.app import _BackgroundRunner

    class _TestPanel(tk.Frame):  # type: ignore[name-defined,misc]
        def __init__(self, parent: _tk.Tk) -> None:
            super().__init__(parent)
            self.called = False

        def on_done(self, _value: int) -> None:
            self.called = True
            raise tk.TclError("invalid command name")

    runner = _BackgroundRunner(root)
    panel = _TestPanel(root)
    panel.destroy()

    with caplog.at_level(logging.INFO):
        runner._dispatch_callback(panel.on_done, "_fetch", 42)

    assert panel.called is False
    assert "target widget no longer exists" in caplog.text


# ── services tests ────────────────────────────────────────────────


def test_services_format_timestamp() -> None:
    from pathkeeper.services import format_backup_timestamp_utc

    ts = datetime(2025, 3, 15, 14, 30, 0, tzinfo=UTC)
    assert format_backup_timestamp_utc(ts) == "2025-03-15 14:30Z"
