"""Tkinter GUI for pathkeeper.

Launch via ``pathkeeper gui`` or ``pathkeeper --gui``.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import tkinter as tk
from functools import partial
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, cast

from pathkeeper import __version__
from pathkeeper.errors import PermissionDeniedError
from pathkeeper.models import Scope

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pathkeeper.core.edit import EditSession
    from pathkeeper.core.path_writer import PathWriter
    from pathkeeper.core.split_long import SplitLongPlan
    from pathkeeper.models import (
        BackupRecord,
        DiagnosticEntry,
        DiagnosticReport,
        PathSnapshot,
    )


# ── colours ──────────────────────────────────────────────────────────
_CLR_OK = "#22c55e"
_CLR_WARN = "#eab308"
_CLR_ERR = "#ef4444"
_CLR_DIM = "#9ca3af"
_CLR_BG = "#1e1e2e"
_CLR_BG_ALT = "#252536"
_CLR_FG = "#cdd6f4"
_CLR_ACCENT = "#89b4fa"
_CLR_SIDEBAR = "#181825"
_CLR_BTN = "#313244"
_CLR_BTN_ACTIVE = "#45475a"

logger = logging.getLogger(__name__)


# ── background runner ────────────────────────────────────────────────
class _BackgroundRunner:
    """Run a callable in a daemon thread; post result back via *root.after*."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root

    @staticmethod
    def _callback_target_alive(callback: object) -> bool:
        owner = getattr(callback, "__self__", None)
        if not isinstance(owner, tk.Misc):
            return True
        try:
            return bool(owner.winfo_exists())
        except tk.TclError:
            return False

    def _dispatch_callback(
        self, callback: object, task_name: str, *args: object
    ) -> None:
        if not self._callback_target_alive(callback):
            logger.info(
                "Skipping background callback for %s because its target widget no longer exists.",
                task_name,
            )
            return
        try:
            callback(*args)  # type: ignore[operator]
        except (RuntimeError, tk.TclError) as exc:
            logger.info(
                "Dropped background callback for %s after widget teardown: %s",
                task_name,
                exc,
            )

    def run(
        self,
        func: object,
        *,
        args: tuple[object, ...] = (),
        on_success: object = None,
        on_error: object = None,
    ) -> None:
        task_name = getattr(func, "__name__", func.__class__.__name__)

        def _worker() -> None:
            try:
                logger.info("Starting background task: %s", task_name)
                result = func(*args)  # type: ignore[operator]
                logger.info("Background task completed: %s", task_name)
                if on_success is not None:
                    with contextlib.suppress(RuntimeError):
                        self._root.after(
                            0, self._dispatch_callback, on_success, task_name, result
                        )
            except Exception as exc:
                logger.exception("Background task failed: %s", task_name)
                with contextlib.suppress(RuntimeError):
                    if on_error is not None:
                        self._root.after(
                            0, self._dispatch_callback, on_error, task_name, exc
                        )
                    else:
                        self._root.after(
                            0,
                            self._dispatch_callback,
                            lambda exc: messagebox.showerror("Error", str(exc)),
                            task_name,
                            exc,
                        )

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()


def _tree_item_values(tree: ttk.Treeview, item_id: str) -> Sequence[object]:
    values = tree.item(item_id, "values")
    return cast("Sequence[object]", values)


# ── main application ─────────────────────────────────────────────────
class PathkeeperApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        logger.info("Initializing pathkeeper GUI.")
        self.title(f"pathkeeper {__version__}")
        self.geometry("1050x680")
        self.minsize(800, 500)
        self.configure(bg=_CLR_BG)

        self._runner = _BackgroundRunner(self)
        self._panels: dict[str, tk.Frame] = {}
        self._active_panel: str = ""

        self._build_ui()
        self._show_panel("dashboard")

    # ── layout ────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        # Sidebar
        self._sidebar = tk.Frame(self, bg=_CLR_SIDEBAR, width=180)
        self._sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self._sidebar.pack_propagate(False)

        title = tk.Label(
            self._sidebar,
            text="pathkeeper",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_SIDEBAR,
            pady=12,
        )
        title.pack(fill=tk.X)

        self._sidebar_buttons: dict[str, tk.Button] = {}
        items = [
            ("dashboard", "Dashboard"),
            ("inspect", "Inspect"),
            ("doctor", "Doctor"),
            ("backup", "Backups"),
            ("edit", "Edit PATH"),
            ("dedupe", "Dedupe"),
            ("populate", "Populate"),
            ("locate", "Locate"),
            ("repair", "Repair"),
            ("split_long", "Split Long"),
            ("schedule", "Schedule"),
            ("shadow", "Shadows"),
            ("diff_current", "Diff vs Current"),
            ("runtime", "Runtime Entries"),
            ("selfcheck", "Self-Check"),
        ]
        for key, label in items:
            btn = tk.Button(
                self._sidebar,
                text=label,
                anchor="w",
                padx=16,
                pady=6,
                font=("Segoe UI", 10),
                fg=_CLR_FG,
                bg=_CLR_BTN,
                activebackground=_CLR_BTN_ACTIVE,
                activeforeground=_CLR_FG,
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                command=partial(self._show_panel, key),
            )
            btn.pack(fill=tk.X, padx=8, pady=2)
            self._sidebar_buttons[key] = btn

        # Content area
        self._content = tk.Frame(self, bg=_CLR_BG)
        self._content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Status bar
        self._status_var = tk.StringVar(value="Ready")
        self._statusbar = tk.Label(
            self,
            textvariable=self._status_var,
            anchor="w",
            padx=8,
            font=("Segoe UI", 9),
            fg=_CLR_DIM,
            bg=_CLR_SIDEBAR,
        )
        self._statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def _show_panel(self, name: str) -> None:
        if name == self._active_panel:
            return
        logger.info("Showing GUI panel: %s", name)
        # Highlight sidebar button
        for key, btn in self._sidebar_buttons.items():
            btn.configure(
                bg=_CLR_ACCENT if key == name else _CLR_BTN,
                fg="#11111b" if key == name else _CLR_FG,
            )
        # Destroy previous panel
        for child in self._content.winfo_children():
            child.destroy()
        self._active_panel = name
        # Create new panel
        panel = _build_panel(name, self._content, self._runner, self._status_var)
        panel.pack(fill=tk.BOTH, expand=True)
        self._panels[name] = panel

    def set_status(self, text: str) -> None:
        self._status_var.set(text)


# ── panel factory ─────────────────────────────────────────────────
def _build_panel(
    name: str,
    parent: tk.Frame,
    runner: _BackgroundRunner,
    status_var: tk.StringVar,
) -> tk.Frame:
    builders: dict[str, type[_BasePanel]] = {
        "dashboard": DashboardPanel,
        "inspect": InspectPanel,
        "doctor": DoctorPanel,
        "backup": BackupPanel,
        "edit": EditPanel,
        "dedupe": DedupePanel,
        "populate": PopulatePanel,
        "locate": LocatePanel,
        "repair": RepairPanel,
        "split_long": SplitLongPanel,
        "schedule": SchedulePanel,
        "shadow": ShadowPanel,
        "diff_current": DiffCurrentPanel,
        "runtime": RuntimeEntriesPanel,
        "selfcheck": SelfCheckPanel,
    }
    cls = builders.get(name, DashboardPanel)
    return cls(parent, runner, status_var)


# ── helper: scrolled treeview ─────────────────────────────────────
def _make_tree(
    parent: tk.Misc,
    columns: list[tuple[str, str, int]],
    *,
    height: int = 20,
) -> ttk.Treeview:
    """Create a themed treeview with scrollbar.

    *columns* is a list of (id, heading, width).
    """
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Path.Treeview",
        background=_CLR_BG,
        foreground=_CLR_FG,
        fieldbackground=_CLR_BG,
        rowheight=24,
        font=("Consolas", 10),
    )
    style.configure(
        "Path.Treeview.Heading",
        background=_CLR_SIDEBAR,
        foreground=_CLR_FG,
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "Path.Treeview",
        background=[("selected", _CLR_ACCENT)],
        foreground=[("selected", "#11111b")],
    )

    frame = tk.Frame(parent, bg=_CLR_BG)
    frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

    col_ids = [c[0] for c in columns]
    tree = ttk.Treeview(
        frame, columns=col_ids, show="headings", height=height, style="Path.Treeview"
    )
    for cid, heading, width in columns:
        tree.heading(cid, text=heading)
        tree.column(cid, width=width, minwidth=40)

    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)

    tree.tag_configure("ok", foreground=_CLR_OK)
    tree.tag_configure("warn", foreground=_CLR_WARN)
    tree.tag_configure("error", foreground=_CLR_ERR)
    tree.tag_configure("dim", foreground=_CLR_DIM)
    return tree


def _make_output(parent: tk.Misc, *, height: int = 10) -> tk.Text:
    """Create a scrolled read-only text widget for output display."""
    frame = tk.Frame(parent, bg=_CLR_BG)
    frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
    text = tk.Text(
        frame,
        height=height,
        wrap=tk.WORD,
        bg=_CLR_BG_ALT,
        fg=_CLR_FG,
        font=("Consolas", 10),
        relief=tk.FLAT,
        bd=4,
        insertbackground=_CLR_FG,
    )
    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
    text.configure(yscrollcommand=vsb.set, state=tk.DISABLED)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    return text


def _output_set(text_widget: tk.Text, content: str) -> None:
    text_widget.configure(state=tk.NORMAL)
    text_widget.delete("1.0", tk.END)
    text_widget.insert(tk.END, content)
    text_widget.configure(state=tk.DISABLED)


def _make_scope_selector(
    parent: tk.Misc,
    *,
    default: str = "all",
    command: object = None,
) -> tk.StringVar:
    """Row of radio buttons for scope selection."""
    var = tk.StringVar(value=default)
    frame = tk.Frame(parent, bg=_CLR_BG)
    frame.pack(fill=tk.X, padx=8, pady=(8, 0))
    tk.Label(frame, text="Scope:", fg=_CLR_FG, bg=_CLR_BG, font=("Segoe UI", 10)).pack(
        side=tk.LEFT, padx=(0, 8)
    )
    for label in ("all", "system", "user"):
        tk.Radiobutton(
            frame,
            text=label.capitalize(),
            variable=var,
            value=label,
            fg=_CLR_FG,
            bg=_CLR_BG,
            selectcolor=_CLR_BG_ALT,
            activebackground=_CLR_BG,
            activeforeground=_CLR_FG,
            font=("Segoe UI", 10),
            command=command,  # type: ignore[arg-type]
        ).pack(side=tk.LEFT, padx=4)
    return var


def _make_toolbar(parent: tk.Misc) -> tk.Frame:
    toolbar = tk.Frame(parent, bg=_CLR_BG)
    toolbar.pack(fill=tk.X, padx=8, pady=4)
    return toolbar


def _toolbar_btn(toolbar: tk.Frame, text: str, command: object) -> tk.Button:
    btn = tk.Button(
        toolbar,
        text=text,
        command=command,  # type: ignore[arg-type]
        font=("Segoe UI", 9),
        fg=_CLR_FG,
        bg=_CLR_BTN,
        activebackground=_CLR_BTN_ACTIVE,
        activeforeground=_CLR_FG,
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=4,
        cursor="hand2",
    )
    btn.pack(side=tk.LEFT, padx=4)
    return btn


# ══════════════════════════════════════════════════════════════════
# Panels
# ══════════════════════════════════════════════════════════════════


class _BasePanel(tk.Frame):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, bg=_CLR_BG)
        self._runner = runner
        self._status = status_var


# ── Locate ────────────────────────────────────────────────────────
class LocatePanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Locate Executable",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))

        # Search controls
        search_frame = tk.Frame(self, bg=_CLR_BG)
        search_frame.pack(fill=tk.X, padx=16, pady=8)

        tk.Label(search_frame, text="Executable Name:", bg=_CLR_BG, fg=_CLR_FG).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._name_var = tk.StringVar()
        self._entry = tk.Entry(
            search_frame,
            textvariable=self._name_var,
            width=20,
            bg=_CLR_BG_ALT,
            fg=_CLR_FG,
            insertbackground=_CLR_FG,
            relief=tk.FLAT,
        )
        self._entry.pack(side=tk.LEFT, padx=(0, 16))
        self._entry.bind("<Return>", lambda _: self._search())

        self._all_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            search_frame,
            text="Find All",
            variable=self._all_var,
            bg=_CLR_BG,
            fg=_CLR_FG,
            selectcolor=_CLR_BG_ALT,
            activebackground=_CLR_BG,
            activeforeground=_CLR_FG,
        ).pack(side=tk.LEFT, padx=(0, 16))

        from pathkeeper.platform import normalized_os_name

        self._os_name = normalized_os_name()
        self._drive_var = tk.StringVar(value="C:\\")
        if self._os_name == "windows":
            tk.Label(search_frame, text="Drive:", bg=_CLR_BG, fg=_CLR_FG).pack(
                side=tk.LEFT, padx=(0, 8)
            )
            tk.Entry(
                search_frame,
                textvariable=self._drive_var,
                width=4,
                bg=_CLR_BG_ALT,
                fg=_CLR_FG,
                insertbackground=_CLR_FG,
                relief=tk.FLAT,
            ).pack(side=tk.LEFT, padx=(0, 16))

        _toolbar_btn(search_frame, "Search", self._search)

        self._tree = _make_tree(
            self,
            [
                ("path", "Full Path", 800),
            ],
            height=15,
        )

        self._output = _make_output(self, height=4)
        _output_set(
            self._output,
            "Enter an executable name to search for it anywhere on the computer.\n"
            "This will use ripgrep (rg) if available, or a fast system search.",
        )

        # Context menu
        self._menu = tk.Menu(self, tearoff=0, bg=_CLR_SIDEBAR, fg=_CLR_FG)
        self._menu.add_command(label="Copy Path", command=self._copy_path)
        self._menu.add_command(label="Open Folder", command=self._open_folder)
        self._menu.add_separator()
        self._menu.add_command(
            label="Add Parent Folder to PATH", command=self._add_to_path
        )
        self._tree.bind("<Button-3>", self._show_menu)

    def _search(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            return
        find_all = self._all_var.get()
        drive = self._drive_var.get() if self._os_name == "windows" else None

        self._status.set(f"Searching for '{name}'...")
        for item in self._tree.get_children():
            self._tree.delete(item)

        self._runner.run(
            self._do_search,
            args=(name, find_all, drive),
            on_success=self._on_search_success,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_search(name: str, find_all: bool, drive: str | None) -> list[str]:
        from pathkeeper.services import locate_executable_service

        results = locate_executable_service(name, find_all=find_all, drive=drive)
        return [str(p) for p in results]

    def _on_search_success(self, results: list[str]) -> None:
        for r in results:
            self._tree.insert("", tk.END, values=(r,))
        count = len(results)
        msg = f"Found {count} result(s)"
        self._status.set(msg)
        _output_set(self._output, msg)

    def _on_error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        _output_set(self._output, f"Error: {exc}")

    def _show_menu(self, event: tk.Event) -> None:
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._menu.post(event.x_root, event.y_root)

    def _copy_path(self) -> None:
        sel = self._tree.selection()
        if sel:
            path = str(_tree_item_values(self._tree, sel[0])[0])
            self.clipboard_clear()
            self.clipboard_append(path)

    def _open_folder(self) -> None:
        import os
        import subprocess

        sel = self._tree.selection()
        if sel:
            path = str(_tree_item_values(self._tree, sel[0])[0])
            folder = os.path.dirname(path)
            if self._os_name == "windows":
                # Use getattr for mypy on Linux
                startfile = getattr(os, "startfile", None)
                if startfile:  # pylint: disable=using-constant-test
                    startfile(folder)
            else:
                subprocess.run(["xdg-open", folder], check=False)

    def _add_to_path(self) -> None:
        import os

        sel = self._tree.selection()
        if not sel:
            return
        path = str(_tree_item_values(self._tree, sel[0])[0])
        folder = os.path.dirname(path)
        if not messagebox.askyesno("Add to PATH", f"Add '{folder}' to your USER PATH?"):
            return

        self._status.set(f"Adding {folder} to PATH...")
        self._runner.run(
            self._do_add,
            args=(folder,),
            on_success=lambda msg: messagebox.showinfo("Success", msg),
            on_error=self._on_error,
        )

    @staticmethod
    def _do_add(folder: str) -> str:
        from pathkeeper.core.diagnostics import join_path
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.services import backup_now, get_snapshot_and_adapter

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.USER
        backup_now(tag="pre-locate-add", note=f"Before adding {folder} via Locate")
        new_entries = [*snapshot.user_path, folder]
        updated = snapshot.with_scope_entries(
            scope, new_entries, join_path(new_entries, os_name)
        )
        write_changed_snapshot(adapter, snapshot, updated, scope)
        return f"Added '{folder}' to USER PATH."


# ── Dashboard ─────────────────────────────────────────────────────
class DashboardPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="PATH Health Dashboard",
            font=("Segoe UI", 16, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(16, 4))
        self._summary_label = tk.Label(
            self,
            text="Loading...",
            font=("Consolas", 11),
            fg=_CLR_FG,
            bg=_CLR_BG,
            wraplength=700,
            justify=tk.LEFT,
        )
        self._summary_label.pack(pady=8, padx=16, anchor="w")
        self._warnings_label = tk.Label(
            self,
            text="",
            font=("Consolas", 10),
            fg=_CLR_WARN,
            bg=_CLR_BG,
            wraplength=700,
            justify=tk.LEFT,
        )
        self._warnings_label.pack(pady=4, padx=16, anchor="w")

        self._backup_label = tk.Label(
            self,
            text="",
            font=("Consolas", 10),
            fg=_CLR_DIM,
            bg=_CLR_BG,
            wraplength=700,
            justify=tk.LEFT,
        )
        self._backup_label.pack(pady=4, padx=16, anchor="w")

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Refresh", self._load)
        self._load()

    def _load(self) -> None:
        self._status.set("Loading PATH data...")
        self._runner.run(self._fetch, on_success=self._display, on_error=self._on_error)

    @staticmethod
    def _fetch() -> tuple[DiagnosticReport, int]:
        from pathkeeper.services import read_current_report, recent_backups

        _snap, report = read_current_report(Scope.ALL)
        backup_count = len(recent_backups(limit=9999))
        return report, backup_count

    def _display(self, result: tuple[DiagnosticReport, int]) -> None:
        report, backup_count = result
        s = report.summary
        health = (
            "healthy"
            if s.invalid == 0 and s.duplicates == 0 and s.empty == 0
            else "needs attention"
        )
        self._summary_label.configure(
            text=(
                f"Entries: {s.total}    Valid: {s.valid}    "
                f"Invalid: {s.invalid}    Duplicates: {s.duplicates}    "
                f"Empty: {s.empty}\n"
                f"PATH length: {report.path_length} chars    Health: {health}"
            ),
        )
        if s.warnings:
            self._warnings_label.configure(text="\n".join(f"! {w}" for w in s.warnings))
        else:
            self._warnings_label.configure(text="")
        self._backup_label.configure(text=f"{backup_count} backup(s) on file")
        self._status.set("Dashboard loaded")

    def _on_error(self, exc: Exception) -> None:
        self._summary_label.configure(text=f"Error: {exc}")
        self._status.set("Error loading dashboard")


# ── Inspect / Doctor ──────────────────────────────────────────────
class InspectPanel(_BasePanel):
    _doctor_mode: bool = False

    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Inspect PATH",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(self, command=self._load)
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Run", self._load)

        self._tree = _make_tree(
            self,
            [
                ("idx", "#", 40),
                ("status", "Status", 60),
                ("scope", "Scope", 70),
                ("path", "Path", 420),
                ("executables", "Executables", 200),
                ("notes", "Notes", 160),
            ],
        )
        self._summary_output = _make_output(self, height=7)
        self._load()

    def _load(self) -> None:
        scope_str = self._scope_var.get()
        self._status.set(f"Inspecting PATH ({scope_str})...")
        self._runner.run(
            self._fetch,
            args=(scope_str,),
            on_success=self._display,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch(scope_str: str) -> DiagnosticReport:
        from pathkeeper.services import read_current_report

        _snap, report = read_current_report(Scope.from_value(scope_str))
        return report

    def _display(self, report: DiagnosticReport) -> None:
        self._populate_tree(report)
        s = report.summary
        _output_set(
            self._summary_output,
            (
                f"Entries: {s.total}  Valid: {s.valid}  Invalid: {s.invalid}  "
                f"Duplicates: {s.duplicates}  Empty: {s.empty}\n"
                + ("\n".join(f"! {w}" for w in s.warnings) if s.warnings else "")
            ),
        )
        self._status.set("Inspect complete")

    def _populate_tree(self, report: DiagnosticReport) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for entry in report.entries:
            tag, marker, notes = _entry_display(entry)
            exe_str = (
                _format_executables(entry.executables)
                if (entry.is_dir and not entry.is_duplicate)
                else ""
            )
            self._tree.insert(
                "",
                tk.END,
                values=(
                    entry.index,
                    marker,
                    entry.scope.value,
                    entry.value,
                    exe_str,
                    notes,
                ),
                tags=(tag,),
            )

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._summary_output, f"Error: {exc}")
        self._status.set("Error")


class DoctorPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Doctor",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(self, command=self._load)
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Diagnose", self._load)

        self._tree = _make_tree(
            self,
            [
                ("status", "Status", 60),
                ("check", "Check", 280),
                ("detail", "Detail", 200),
                ("remediation", "Remediation", 350),
            ],
            height=10,
        )
        self._tree.bind("<<TreeviewSelect>>", self._on_check_select)
        self._detail_output = _make_output(self, height=12)
        self._last_checks: list[object] = []
        self._load()

    def _load(self) -> None:
        scope_str = self._scope_var.get()
        self._status.set(f"Running doctor ({scope_str})...")
        self._runner.run(
            self._fetch,
            args=(scope_str,),
            on_success=self._display,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch(scope_str: str) -> tuple[DiagnosticReport, list[object]]:
        from pathkeeper.core.diagnostics import doctor_checks
        from pathkeeper.services import read_current_report

        _snap, report = read_current_report(Scope.from_value(scope_str))
        checks = doctor_checks(report)
        return report, list(checks)

    def _display(self, result: tuple[DiagnosticReport, list[object]]) -> None:
        from pathkeeper.core.diagnostics import DoctorCheck

        report, checks_raw = result
        checks: list[DoctorCheck] = checks_raw  # type: ignore[assignment]
        self._last_checks = checks_raw
        for item in self._tree.get_children():
            self._tree.delete(item)
        issue_count = 0
        for check in checks:
            if check.status == "pass":
                tag = "ok"
                marker = "PASS"
            elif check.status == "warn":
                tag = "warn"
                marker = "WARN"
                issue_count += len(check.affected) if check.affected else 1
            else:
                tag = "error"
                marker = "FAIL"
                issue_count += len(check.affected) if check.affected else 1
            self._tree.insert(
                "",
                tk.END,
                values=(marker, check.name, check.detail, check.remediation),
                tags=(tag,),
            )
        s = report.summary
        if issue_count == 0:
            overall = f"Overall: healthy  ({s.total} entries checked)"
        else:
            label = "issue" if issue_count == 1 else "issues"
            overall = (
                f"Overall: needs attention  ({issue_count} {label}, "
                f"{s.total} entries checked)"
            )
        _output_set(self._detail_output, overall)
        self._status.set("Doctor complete")

    def _on_check_select(self, _event: object) -> None:
        from pathkeeper.core.diagnostics import DoctorCheck, explain_entry

        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        checks: list[DoctorCheck] = self._last_checks  # type: ignore[assignment]
        if idx >= len(checks):
            return
        check = checks[idx]
        if not check.affected:
            _output_set(self._detail_output, f"{check.name}: {check.detail}")
            return
        lines: list[str] = [f"{check.name}: {check.detail}"]
        if check.remediation:
            lines.append(f"  -> {check.remediation}")
        lines.append("")
        lines.append("Affected entries:")
        for entry in check.affected:
            scope_label = f"({entry.scope.value})"
            dup = f" dup-of #{entry.duplicate_of}" if entry.duplicate_of else ""
            lines.append(f"  #{entry.index} {scope_label} {entry.value}{dup}")
            lines.append(f"    {explain_entry(entry, 'linux')}")
        _output_set(self._detail_output, "\n".join(lines))

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._detail_output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


def _entry_display(entry: DiagnosticEntry) -> tuple[str, str, str]:
    """Return (tag, status_marker, notes) for a diagnostic entry."""
    if entry.is_empty:
        return "dim", "!", "empty"
    if entry.is_duplicate and entry.duplicate_of is not None:
        return "warn", "D", f"duplicate of #{entry.duplicate_of}"
    if entry.likely_missing_separator:
        return "warn", "!!", "likely missing separator"
    if not entry.exists:
        return "error", "x", "missing"
    if not entry.is_dir:
        return "error", "~", "file, not directory"
    return "ok", "ok", ""


def _format_executables(names: list[str], *, limit: int = 10) -> str:
    """Format a list of executable names for display in the GUI tree."""
    if not names:
        return ""
    shown = names[:limit]
    suffix = ", …" if len(names) > limit else ""
    return ", ".join(shown) + suffix


# ── Backups ───────────────────────────────────────────────────────
class BackupPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Backups",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Refresh", self._load_list)
        _toolbar_btn(toolbar, "Create Backup", self._create_backup)
        _toolbar_btn(toolbar, "Show Details", self._show_selected)
        _toolbar_btn(toolbar, "Restore Selected", self._restore_selected)

        # Note entry
        note_frame = tk.Frame(self, bg=_CLR_BG)
        note_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(
            note_frame, text="Note:", fg=_CLR_FG, bg=_CLR_BG, font=("Segoe UI", 10)
        ).pack(side=tk.LEFT)
        self._note_var = tk.StringVar()
        tk.Entry(
            note_frame,
            textvariable=self._note_var,
            width=50,
            bg=_CLR_BG_ALT,
            fg=_CLR_FG,
            insertbackground=_CLR_FG,
            font=("Consolas", 10),
            relief=tk.FLAT,
        ).pack(side=tk.LEFT, padx=8)

        self._tree = _make_tree(
            self,
            [
                ("num", "#", 35),
                ("file", "Filename", 220),
                ("ts", "Timestamp", 130),
                ("tag", "Tag", 70),
                ("hash", "Hash", 100),
                ("sys", "Sys", 45),
                ("usr", "Usr", 45),
                ("note", "Note", 200),
            ],
            height=12,
        )
        self._detail_output = _make_output(self, height=14)
        self._load_list()

    def _load_list(self) -> None:
        self._status.set("Loading backups...")
        self._runner.run(
            self._fetch_list, on_success=self._display_list, on_error=self._on_error
        )

    @staticmethod
    def _fetch_list() -> list[BackupRecord]:
        from pathkeeper.services import recent_backups

        return recent_backups(limit=50)

    def _display_list(self, records: list[BackupRecord]) -> None:
        from pathkeeper.core.backup import backup_content_hash
        from pathkeeper.services import format_backup_timestamp_utc

        for item in self._tree.get_children():
            self._tree.delete(item)
        for i, rec in enumerate(records, 1):
            fname = rec.source_file.name if rec.source_file else "<unsaved>"
            self._tree.insert(
                "",
                tk.END,
                values=(
                    i,
                    fname,
                    format_backup_timestamp_utc(rec.timestamp),
                    rec.tag,
                    backup_content_hash(rec),
                    len(rec.system_path),
                    len(rec.user_path),
                    rec.note,
                ),
            )
        self._status.set(f"{len(records)} backup(s) loaded")

    def _create_backup(self) -> None:
        note = self._note_var.get().strip()
        self._status.set("Creating backup...")
        self._runner.run(
            self._do_create,
            args=(note,),
            on_success=self._on_created,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_create(note: str) -> str | None:
        from pathkeeper.services import backup_now

        dest = backup_now(tag="manual", note=note)
        return str(dest) if dest else None

    def _on_created(self, result: str | None) -> None:
        if result is None:
            self._status.set("Backup skipped (unchanged)")
            messagebox.showinfo(
                "Backup", "Skipped — PATH is unchanged since last backup."
            )
        else:
            self._status.set(f"Backup created: {result}")
            messagebox.showinfo("Backup", f"Created: {result}")
        self._load_list()

    def _show_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            messagebox.showwarning(
                "No selection", "Select a backup from the list first."
            )
            return
        values = _tree_item_values(self._tree, selection[0])
        identifier = str(values[1])  # filename
        self._runner.run(
            self._fetch_detail,
            args=(identifier,),
            on_success=self._display_detail,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch_detail(identifier: str) -> BackupRecord:
        from pathkeeper.services import select_backup

        rec, _ = select_backup(identifier)
        return rec

    def _display_detail(self, rec: BackupRecord) -> None:
        from pathkeeper.core.backup import backup_content_hash
        from pathkeeper.services import format_backup_timestamp_utc

        lines = [
            f"File: {rec.source_file.name if rec.source_file else '<unsaved>'}",
            f"Timestamp: {format_backup_timestamp_utc(rec.timestamp)}",
            f"Tag: {rec.tag}    Hash: {backup_content_hash(rec)}",
            f"Host: {rec.hostname}    OS: {rec.os_name}",
            f"Note: {rec.note or '-'}",
            "",
            f"System PATH ({len(rec.system_path)} entries):",
        ]
        for i, e in enumerate(rec.system_path, 1):
            lines.append(f"  {i:>3}. {e}")
        lines.append("")
        lines.append(f"User PATH ({len(rec.user_path)} entries):")
        for i, e in enumerate(rec.user_path, 1):
            lines.append(f"  {i:>3}. {e}")
        _output_set(self._detail_output, "\n".join(lines))

    def _restore_selected(self) -> None:
        selection = self._tree.selection()
        if not selection:
            messagebox.showwarning("No selection", "Select a backup to restore.")
            return
        values = _tree_item_values(self._tree, selection[0])
        identifier = str(values[1])
        if not messagebox.askyesno(
            "Restore",
            f"Restore PATH from {identifier}?\n\nA pre-restore backup will be created.",
        ):
            return
        self._status.set("Restoring...")
        self._runner.run(
            self._do_restore,
            args=(identifier,),
            on_success=self._on_restored,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_restore(identifier: str) -> str:
        from pathkeeper.core.diff import compute_diff, render_diff
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.services import (
            backup_now,
            get_snapshot_and_adapter,
            select_backup,
        )

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        rec, _ = select_backup(identifier)
        backup_now(tag="pre-restore", note=f"Before restore {identifier}")
        write_changed_snapshot(adapter, snapshot, rec.snapshot, Scope.ALL)
        diff = compute_diff(
            snapshot.entries_for_scope(Scope.ALL),
            rec.snapshot.entries_for_scope(Scope.ALL),
            os_name,
        )
        return render_diff(diff)

    def _on_restored(self, diff_text: str) -> None:
        self._status.set("Restore complete")
        _output_set(self._detail_output, f"Restore complete.\n\n{diff_text}")
        messagebox.showinfo("Restore", "PATH restored successfully.")

    def _on_error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("Error", str(exc))


# ── Edit PATH ─────────────────────────────────────────────────────
class EditPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Edit PATH",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(
            self, default="user", command=self._load_session
        )

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Load", self._load_session)
        _toolbar_btn(toolbar, "Add", self._add_entry)
        _toolbar_btn(toolbar, "Delete", self._delete_entry)
        _toolbar_btn(toolbar, "Move Up", self._move_up)
        _toolbar_btn(toolbar, "Move Down", self._move_down)
        _toolbar_btn(toolbar, "Edit", self._edit_entry)
        _toolbar_btn(toolbar, "Undo", self._undo)
        _toolbar_btn(toolbar, "Preview Diff", self._preview)
        _toolbar_btn(toolbar, "Write", self._write)

        self._tree = _make_tree(
            self,
            [
                ("idx", "#", 40),
                ("status", "Status", 60),
                ("path", "Path", 620),
                ("notes", "Notes", 200),
            ],
        )
        self._diff_output = _make_output(self, height=6)

        self._session: EditSession | None = None
        self._snapshot: PathSnapshot | None = None
        self._adapter: PathWriter | None = None
        self._os_name = ""
        self._edit_scope: Scope = Scope.USER
        self._load_session()

    def _load_session(self) -> None:
        scope_str = self._scope_var.get()
        if scope_str == "all":
            scope_str = "user"
            self._scope_var.set("user")
        self._status.set("Loading PATH for editing...")
        self._runner.run(
            self._fetch,
            args=(scope_str,),
            on_success=self._init_session,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch(scope_str: str) -> tuple[object, ...]:
        from pathkeeper.services import get_snapshot_and_adapter

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        entries = snapshot.entries_for_scope(scope)
        return snapshot, adapter, os_name, scope, entries

    def _init_session(self, result: tuple[object, ...]) -> None:
        from pathkeeper.core.edit import EditSession

        snapshot, adapter, os_name, scope, entries = result
        self._snapshot = snapshot  # type: ignore[assignment]
        self._adapter = adapter  # type: ignore[assignment]
        self._os_name = str(os_name)
        if isinstance(scope, Scope):
            self._edit_scope = scope
        self._session = EditSession(entries, str(os_name))  # type: ignore[arg-type]
        self._refresh_tree()
        self._status.set("Edit session loaded")

    def _refresh_tree(self) -> None:
        if self._session is None:
            return
        from pathkeeper.core.diagnostics import analyze_snapshot, join_path

        scope = self._edit_scope
        entries = self._session.entries
        report = analyze_snapshot(
            system_entries=entries if scope is Scope.SYSTEM else [],
            user_entries=entries if scope is Scope.USER else [],
            os_name=self._os_name,
            scope=scope,
            raw_value=join_path(entries, self._os_name),
        )
        for item in self._tree.get_children():
            self._tree.delete(item)
        for entry in report.entries:
            tag, marker, notes = _entry_display(entry)
            self._tree.insert(
                "",
                tk.END,
                values=(
                    entry.index,
                    marker,
                    entry.value,
                    notes,
                ),
                tags=(tag,),
            )

    def _add_entry(self) -> None:
        if self._session is None:
            return
        path = filedialog.askdirectory(title="Select directory to add to PATH")
        if not path:
            return
        self._session.add(path)
        self._refresh_tree()
        self._status.set(f"Added: {path}")

    def _delete_entry(self) -> None:
        if self._session is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        self._session.delete(idx)
        self._refresh_tree()
        self._status.set("Entry deleted")

    def _move_up(self) -> None:
        if self._session is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx <= 0:
            return
        self._session.move(idx, idx - 1)
        self._refresh_tree()
        # Reselect
        children = self._tree.get_children()
        if idx - 1 < len(children):
            self._tree.selection_set(children[idx - 1])

    def _move_down(self) -> None:
        if self._session is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        if idx >= len(self._session.entries) - 1:
            return
        self._session.move(idx, idx + 1)
        self._refresh_tree()
        children = self._tree.get_children()
        if idx + 1 < len(children):
            self._tree.selection_set(children[idx + 1])

    def _edit_entry(self) -> None:
        if self._session is None:
            return
        sel = self._tree.selection()
        if not sel:
            return
        idx = self._tree.index(sel[0])
        current = self._session.entries[idx]
        new_path = filedialog.askdirectory(
            title="Select replacement directory", initialdir=current
        )
        if not new_path:
            return
        self._session.replace(idx, new_path)
        self._refresh_tree()
        self._status.set(f"Replaced entry {idx+1}")

    def _undo(self) -> None:
        if self._session is None:
            return
        if self._session.undo():
            self._refresh_tree()
            self._status.set("Undo")
        else:
            self._status.set("Nothing to undo")

    def _preview(self) -> None:
        if self._session is None:
            return
        from pathkeeper.core.diff import render_diff

        diff = self._session.diff()
        _output_set(self._diff_output, render_diff(diff))

    def _write(self) -> None:
        if self._session is None or self._snapshot is None:
            return
        diff = self._session.diff()
        if not diff.added and not diff.removed and not diff.reordered:
            messagebox.showinfo("No changes", "No staged changes to write.")
            return
        from pathkeeper.core.diff import render_diff

        diff_text = render_diff(diff)
        if not messagebox.askyesno(
            "Write PATH", f"Apply these changes?\n\n{diff_text}"
        ):
            return
        self._status.set("Writing PATH...")
        self._runner.run(
            self._do_write,
            args=(
                self._adapter,
                self._snapshot,
                self._session.entries,
                self._edit_scope,
                self._os_name,
            ),
            on_success=self._on_written,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_write(
        adapter: PathWriter,
        snapshot: PathSnapshot,
        entries: list[str],
        scope: Scope,
        os_name: str,
    ) -> str:
        from pathkeeper.core.diagnostics import join_path
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.services import backup_now

        updated = snapshot.with_scope_entries(
            scope, entries, join_path(entries, os_name)
        )
        backup_now(tag="pre-edit", note="Before GUI edit")
        write_changed_snapshot(adapter, snapshot, updated, scope)
        return "PATH written successfully."

    def _on_written(self, msg: str) -> None:
        self._status.set(msg)
        messagebox.showinfo("Edit", msg)
        self._load_session()

    def _on_error(self, exc: Exception) -> None:
        self._status.set(f"Error: {exc}")
        messagebox.showerror("Error", str(exc))


# ── Dedupe ────────────────────────────────────────────────────────
class DedupePanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Dedupe PATH",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(self, command=self._preview)
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Preview", self._preview)
        _toolbar_btn(toolbar, "Apply", self._apply)
        self._output = _make_output(self, height=20)
        self._preview()

    def _preview(self) -> None:
        scope_str = self._scope_var.get()
        self._status.set("Computing dedupe preview...")
        self._runner.run(
            self._compute,
            args=(scope_str,),
            on_success=lambda r: self._show_result(r, preview=True),
            on_error=self._on_error,
        )

    def _apply(self) -> None:
        scope_str = self._scope_var.get()
        if not messagebox.askyesno(
            "Dedupe", "Apply dedupe changes? A backup will be created first."
        ):
            return
        self._status.set("Applying dedupe...")
        self._runner.run(
            self._do_apply,
            args=(scope_str,),
            on_success=lambda r: self._show_result(r, preview=False),
            on_error=self._on_error,
        )

    @staticmethod
    def _compute(scope_str: str) -> str:
        from pathkeeper.core.dedupe import dedupe_entries
        from pathkeeper.core.diagnostics import canonicalize_entry
        from pathkeeper.core.diff import compute_diff, render_diff
        from pathkeeper.services import get_snapshot_and_adapter

        snapshot, _adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        lines: list[str] = []
        has_changes = False
        sys_res = None
        if scope in (Scope.SYSTEM, Scope.ALL):
            sys_res = dedupe_entries(snapshot.system_path, os_name)
            diff_text = render_diff(
                compute_diff(sys_res.original, sys_res.cleaned, os_name)
            )
            lines.append("System PATH:")
            lines.append(diff_text)
            lines.append("")
            if sys_res.original != sys_res.cleaned:
                has_changes = True
        if scope in (Scope.USER, Scope.ALL):
            # First pass: dedup within user PATH only (intra-scope duplicates)
            usr_intra = dedupe_entries(snapshot.user_path, os_name)
            # Second pass: also remove user entries already present in system PATH
            pre_seen = (
                {canonicalize_entry(e, os_name) for e in sys_res.cleaned}
                if sys_res is not None
                else None
            )
            usr_res = dedupe_entries(snapshot.user_path, os_name, pre_seen=pre_seen)

            # Separate the two kinds of removal for clarity in the display
            intra_removed = set(
                usr_intra.removed_duplicates
                + usr_intra.removed_invalid
                + usr_intra.removed_empty
            )
            cross_scope_removed = [
                e for e in usr_res.removed_duplicates if e not in intra_removed
            ]

            lines.append("User PATH (within-scope duplicates & invalid):")
            lines.append(
                render_diff(
                    compute_diff(usr_intra.original, usr_intra.cleaned, os_name)
                )
            )
            if cross_scope_removed:
                lines.append("")
                lines.append("User PATH (entries already in System PATH — redundant):")
                lines.extend(f"  - {e}" for e in cross_scope_removed)
            if usr_res.original != usr_res.cleaned:
                has_changes = True
        if not has_changes:
            return "No duplicates or invalid entries found. PATH looks clean!"
        return "\n".join(lines)

    @staticmethod
    def _do_apply(scope_str: str) -> str:
        from pathkeeper.core.dedupe import dedupe_entries
        from pathkeeper.core.diagnostics import join_path
        from pathkeeper.core.diff import compute_diff, render_diff
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.models import PathSnapshot
        from pathkeeper.services import backup_now, get_snapshot_and_adapter

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        backup_now(tag="pre-dedupe", note="Before GUI dedupe")
        if scope is Scope.ALL:
            sys_res = dedupe_entries(snapshot.system_path, os_name)
            usr_res = dedupe_entries(snapshot.user_path, os_name)
            updated = PathSnapshot(
                system_path=sys_res.cleaned,
                user_path=usr_res.cleaned,
                system_path_raw=join_path(sys_res.cleaned, os_name),
                user_path_raw=join_path(usr_res.cleaned, os_name),
            )
        else:
            res = dedupe_entries(snapshot.entries_for_scope(scope), os_name)
            updated = snapshot.with_scope_entries(
                scope, res.cleaned, join_path(res.cleaned, os_name)
            )
        write_changed_snapshot(adapter, snapshot, updated, scope)
        diff = compute_diff(
            snapshot.entries_for_scope(scope),
            updated.entries_for_scope(scope),
            os_name,
        )
        return f"Dedupe applied.\n\n{render_diff(diff)}"

    def _show_result(self, text: str, *, preview: bool) -> None:
        _output_set(self._output, text)
        self._status.set("Preview ready" if preview else "Dedupe complete")

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Populate ──────────────────────────────────────────────────────
class PopulatePanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Populate PATH",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(
            self, default="user", command=self._discover
        )
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Discover", self._discover)
        _toolbar_btn(toolbar, "Add Selected", self._add_selected)

        self._tree = _make_tree(
            self,
            [
                ("cat", "Category", 110),
                ("name", "Tool", 120),
                ("path", "Path", 340),
                ("executables", "Executables", 240),
            ],
        )
        self._output = _make_output(self, height=4)
        self._discover()

    def _discover(self) -> None:
        self._status.set("Discovering tools...")
        self._runner.run(self._fetch, on_success=self._display, on_error=self._on_error)

    @staticmethod
    def _fetch() -> list[tuple[str, str, str, str]]:
        from pathkeeper.config import load_config
        from pathkeeper.core.populate import discover_tools, load_catalog
        from pathkeeper.services import get_snapshot_and_adapter

        snapshot, _adapter, os_name = get_snapshot_and_adapter()
        config = load_config()
        catalog = load_catalog(config)
        existing = snapshot.entries_for_scope(Scope.ALL)
        matches = discover_tools(catalog, existing, os_name=os_name)
        return [
            (m.category, m.name, m.path, _format_executables(m.found_executables))
            for m in matches
        ]

    def _display(self, items: list[tuple[str, str, str, str]]) -> None:
        for child in self._tree.get_children():
            self._tree.delete(child)
        for cat, name, path, exes in items:
            self._tree.insert("", tk.END, values=(cat, name, path, exes))
        msg = (
            f"{len(items)} tool path(s) found"
            if items
            else "No missing tool directories found"
        )
        _output_set(self._output, msg)
        self._status.set(msg)

    def _add_selected(self) -> None:
        selections = self._tree.selection()
        if not selections:
            messagebox.showwarning("No selection", "Select paths to add.")
            return
        paths = [str(_tree_item_values(self._tree, s)[2]) for s in selections]
        scope_str = self._scope_var.get()
        if scope_str == "all":
            scope_str = "user"
        if not messagebox.askyesno(
            "Populate", f"Add {len(paths)} path(s) to {scope_str} PATH?"
        ):
            return
        self._status.set("Adding paths...")
        self._runner.run(
            self._do_add,
            args=(paths, scope_str),
            on_success=self._on_added,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_add(paths: list[str], scope_str: str) -> str:
        from pathkeeper.core.diagnostics import join_path
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.services import backup_now, get_snapshot_and_adapter

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        backup_now(tag="pre-populate", note="Before GUI populate")
        new_entries = [*snapshot.entries_for_scope(scope), *paths]
        updated = snapshot.with_scope_entries(
            scope, new_entries, join_path(new_entries, os_name)
        )
        write_changed_snapshot(adapter, snapshot, updated, scope)
        return f"Added {len(paths)} path(s)"

    def _on_added(self, msg: str) -> None:
        self._status.set(msg)
        messagebox.showinfo("Populate", msg)
        self._discover()

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Repair ────────────────────────────────────────────────────────
class RepairPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Repair Truncated",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(self)
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Scan", self._scan)

        self._output = _make_output(self, height=20)
        self._scan()

    def _scan(self) -> None:
        scope_str = self._scope_var.get()
        self._status.set("Scanning for truncated entries...")
        self._runner.run(
            self._fetch,
            args=(scope_str,),
            on_success=self._display,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch(scope_str: str) -> str:
        from pathkeeper.config import backups_home
        from pathkeeper.core.backup import list_backups
        from pathkeeper.core.repair_truncated import find_truncated_repairs
        from pathkeeper.services import get_snapshot_and_adapter

        snapshot, _adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        repairs = find_truncated_repairs(
            snapshot=snapshot,
            scope=scope,
            os_name=os_name,
            records=list_backups(backups_home()),
        )
        if not repairs:
            return "No likely truncated PATH entries were found."
        lines = ["Possible truncated PATH repairs:\n"]
        for repair in repairs:
            lines.append(
                f"[{repair.scope.value}] Entry #{repair.display_index}: {repair.value}"
            )
            for i, cand in enumerate(repair.candidates, 1):
                lines.append(f"  {i}. {cand.path} ({cand.source})")
            lines.append("")
        return "\n".join(lines)

    def _display(self, text: str) -> None:
        _output_set(self._output, text)
        self._status.set("Scan complete")

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


class SplitLongPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Split Long PATH",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(
            self, default="user", command=self._preview
        )
        self._max_length_var = tk.StringVar(value="2047")
        self._chunk_length_var = tk.StringVar(value="2047")
        self._var_prefix_var = tk.StringVar()

        options = tk.Frame(self, bg=_CLR_BG)
        options.pack(fill=tk.X, padx=8, pady=4)
        for label, variable, width in (
            ("Max PATH length", self._max_length_var, 8),
            ("Chunk length", self._chunk_length_var, 8),
            ("Var prefix", self._var_prefix_var, 24),
        ):
            group = tk.Frame(options, bg=_CLR_BG)
            group.pack(side=tk.LEFT, padx=(0, 12))
            tk.Label(
                group,
                text=label,
                fg=_CLR_FG,
                bg=_CLR_BG,
                font=("Segoe UI", 10),
            ).pack(anchor="w")
            tk.Entry(
                group,
                textvariable=variable,
                width=width,
                bg=_CLR_BG_ALT,
                fg=_CLR_FG,
                insertbackground=_CLR_FG,
                font=("Consolas", 10),
                relief=tk.FLAT,
            ).pack(anchor="w")

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Preview", self._preview)
        _toolbar_btn(toolbar, "Apply", self._apply)
        self._output = _make_output(self, height=18)
        self._preview()

    def _preview(self) -> None:
        self._status.set("Planning split-long changes...")
        self._runner.run(
            self._render_plan,
            args=self._plan_args(),
            on_success=self._display,
            on_error=self._on_error,
        )

    def _apply(self) -> None:
        if not messagebox.askyesno(
            "Split Long",
            "Apply split-long changes? A backup will be created first.",
        ):
            return
        self._status.set("Applying split-long changes...")
        self._runner.run(
            self._do_apply,
            args=self._plan_args(),
            on_success=self._display,
            on_error=self._on_error,
        )

    def _plan_args(self) -> tuple[str, int, int, str | None]:
        prefix = self._var_prefix_var.get().strip() or None
        return (
            self._scope_var.get(),
            int(self._max_length_var.get()),
            int(self._chunk_length_var.get()),
            prefix,
        )

    @staticmethod
    def _build_plan(
        scope_str: str, max_length: int, chunk_length: int, var_prefix: str | None
    ) -> SplitLongPlan:
        from pathkeeper.core.split_long import build_split_long_plan
        from pathkeeper.services import get_snapshot_and_adapter

        snapshot, adapter, os_name = get_snapshot_and_adapter()
        scope = Scope.from_value(scope_str)
        env_reader_name = (
            "read_system_environment"
            if scope is Scope.SYSTEM
            else "read_user_environment"
        )
        read_environment = getattr(adapter, env_reader_name, None)
        if not callable(read_environment):
            raise RuntimeError(
                "split-long requires Windows environment-variable support."
            )
        return build_split_long_plan(
            snapshot,
            scope=scope,
            os_name=os_name,
            environment=read_environment(),
            max_length=max_length,
            chunk_length=chunk_length,
            var_prefix=var_prefix,
        )

    @classmethod
    def _render_plan(
        cls, scope_str: str, max_length: int, chunk_length: int, var_prefix: str | None
    ) -> str:
        from pathkeeper.core.split_long import render_plan

        plan = cls._build_plan(scope_str, max_length, chunk_length, var_prefix)
        return render_plan(plan)

    @classmethod
    def _do_apply(
        cls, scope_str: str, max_length: int, chunk_length: int, var_prefix: str | None
    ) -> str:
        from pathkeeper.core.path_writer import write_changed_snapshot
        from pathkeeper.core.split_long import apply_plan_to_snapshot, render_plan
        from pathkeeper.services import backup_now, get_snapshot_and_adapter

        snapshot, adapter, _os_name = get_snapshot_and_adapter()
        plan = cls._build_plan(scope_str, max_length, chunk_length, var_prefix)
        if not plan.changed:
            return render_plan(plan)
        updated = apply_plan_to_snapshot(snapshot, plan)
        backup_now(tag="pre-split-long", note="Before GUI split-long")
        write_changed_snapshot(adapter, snapshot, updated, plan.scope)
        return render_plan(plan) + "\n\nSplit-long complete."

    def _display(self, text: str) -> None:
        _output_set(self._output, text)
        if "Split-long complete." in text:
            self._status.set("Split-long complete")
        else:
            self._status.set("Split-long preview ready")

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Schedule ──────────────────────────────────────────────────────
class SchedulePanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Schedule",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Check Status", self._check)
        _toolbar_btn(toolbar, "Install", self._install)
        _toolbar_btn(toolbar, "Remove", self._remove)
        self._output = _make_output(self, height=10)
        self._check()

    def _check(self) -> None:
        self._runner.run(
            self._fetch_status, on_success=self._display, on_error=self._on_error
        )

    @staticmethod
    def _fetch_status() -> str:
        from pathkeeper.core.schedule import schedule_status
        from pathkeeper.platform import normalized_os_name

        os_name = normalized_os_name()
        logger.info("Fetching GUI schedule status for os=%s", os_name)
        status = schedule_status(os_name)
        if status.enabled:
            return f"Schedule is enabled: {status.detail}"
        return "Schedule is disabled. Use 'Install' to enable automatic backups."

    @staticmethod
    def _do_install() -> str:
        from pathkeeper.core.schedule import install_schedule
        from pathkeeper.platform import normalized_os_name

        os_name = normalized_os_name()
        logger.info("Installing schedule from GUI for os=%s", os_name)
        try:
            return install_schedule(os_name, "startup")
        except PermissionDeniedError:
            if os_name != "windows":
                raise
            logger.warning(
                "Startup schedule install was denied on Windows; retrying as a per-user logon task."
            )
            result = install_schedule(os_name, "startup", trigger="logon")
            return (
                "Startup task creation needs elevation on Windows, so pathkeeper "
                "installed a per-user logon task instead.\n\n"
                f"{result}"
            )

    @staticmethod
    def _do_remove() -> str:
        from pathkeeper.core.schedule import remove_schedule
        from pathkeeper.platform import normalized_os_name

        os_name = normalized_os_name()
        logger.info("Removing schedule from GUI for os=%s", os_name)
        return remove_schedule(os_name)

    def _install(self) -> None:
        if not messagebox.askyesno("Schedule", "Install automatic startup backups?"):
            return
        self._runner.run(
            self._do_install,
            on_success=self._on_install_success,
            on_error=self._on_error,
        )

    def _remove(self) -> None:
        if not messagebox.askyesno("Schedule", "Remove automatic startup backups?"):
            return
        self._runner.run(
            self._do_remove, on_success=self._display, on_error=self._on_error
        )

    def _display(self, text: str) -> None:
        _output_set(self._output, text)
        self._status.set("Schedule checked")

    def _on_install_success(self, _result: str) -> None:
        logger.info("Schedule install succeeded; refreshing GUI schedule status.")
        self._status.set("Schedule installed; refreshing status...")
        self._runner.run(
            self._fetch_status, on_success=self._display, on_error=self._on_error
        )

    def _on_error(self, exc: Exception) -> None:
        logger.error("GUI schedule action failed: %s", exc)
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Shadows ──────────────────────────────────────────────────────
class ShadowPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Executable Shadows",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        self._scope_var = _make_scope_selector(self, command=self._scan)
        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Scan", self._scan)

        self._tree = _make_tree(
            self,
            [
                ("name", "Executable", 150),
                ("rank", "Rank", 60),
                ("scope", "Scope", 70),
                ("directory", "Directory", 500),
            ],
        )
        self._output = _make_output(self, height=4)
        self._scan()

    def _scan(self) -> None:
        scope_str = self._scope_var.get()
        self._status.set("Scanning for shadows...")
        self._runner.run(
            self._fetch,
            args=(scope_str,),
            on_success=self._display,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch(scope_str: str) -> list[tuple[str, str, str, str]]:
        from pathkeeper.services import find_shadows_report

        _snap, groups = find_shadows_report(Scope.from_value(scope_str))
        rows: list[tuple[str, str, str, str]] = []
        for g in groups:
            for i, e in enumerate(g.entries):
                rank = "winner" if i == 0 else "shadow"
                rows.append((g.name, rank, e.scope.value, e.directory))
        return rows

    def _display(self, rows: list[tuple[str, str, str, str]]) -> None:
        for child in self._tree.get_children():
            self._tree.delete(child)
        for name, rank, scope, directory in rows:
            tag = "ok" if rank == "winner" else "warn"
            self._tree.insert(
                "", tk.END, values=(name, rank, scope, directory), tags=(tag,)
            )
        shadow_count = sum(1 for _, r, _, _ in rows if r == "shadow")
        names = {n for n, r, _, _ in rows if r == "shadow"}
        msg = (
            f"{len(names)} shadowed executable(s), {shadow_count} shadow entries"
            if names
            else "No shadowed executables found"
        )
        _output_set(self._output, msg)
        self._status.set(msg)

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Diff vs Current ──────────────────────────────────────────────
class DiffCurrentPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Diff Backup vs Current",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))

        self._scope_var = _make_scope_selector(self)

        # Backup selector row
        sel_frame = tk.Frame(self, bg=_CLR_BG)
        sel_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(
            sel_frame, text="Backup:", fg=_CLR_FG, bg=_CLR_BG, font=("Segoe UI", 10)
        ).pack(side=tk.LEFT)
        self._backup_var = tk.StringVar()
        self._backup_combo = ttk.Combobox(
            sel_frame, textvariable=self._backup_var, width=50, state="readonly"
        )
        self._backup_combo.pack(side=tk.LEFT, padx=8)

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Refresh Backups", self._load_backups)
        _toolbar_btn(toolbar, "Compare", self._compare)

        self._output = _make_output(self, height=20)
        self._backup_names: list[str] = []
        self._load_backups()

    def _load_backups(self) -> None:
        self._status.set("Loading backups...")
        self._runner.run(
            self._fetch_backups,
            on_success=self._populate_combo,
            on_error=self._on_error,
        )

    @staticmethod
    def _fetch_backups() -> list[str]:
        from pathkeeper.services import format_backup_timestamp_utc, recent_backups

        records = recent_backups(limit=50)
        return [
            f"{i}  {r.source_file.name if r.source_file else '<unsaved>'}  "
            f"{format_backup_timestamp_utc(r.timestamp)}"
            for i, r in enumerate(records, 1)
        ]

    def _populate_combo(self, names: list[str]) -> None:
        self._backup_names = names
        self._backup_combo["values"] = names
        if names:
            self._backup_combo.current(0)
        self._status.set(f"{len(names)} backup(s) available")

    def _compare(self) -> None:
        if not self._backup_names:
            messagebox.showwarning("No backups", "No backups available to compare.")
            return
        selection = self._backup_var.get()
        if not selection:
            return
        # Extract the number at the beginning
        identifier = selection.split()[0]
        scope_str = self._scope_var.get()
        self._status.set("Comparing...")
        self._runner.run(
            self._do_compare,
            args=(identifier, scope_str),
            on_success=self._show_result,
            on_error=self._on_error,
        )

    @staticmethod
    def _do_compare(identifier: str, scope_str: str) -> str:
        from pathkeeper.services import diff_backup_vs_current

        scope = Scope.from_value(scope_str)
        name, sys_text, usr_text = diff_backup_vs_current(identifier, scope)
        lines = [f"Backup: {name}  ->  Current PATH\n"]
        if sys_text:
            lines.append("System PATH:")
            lines.append(sys_text)
            lines.append("")
        if usr_text:
            lines.append("User PATH:")
            lines.append(usr_text)
        return "\n".join(lines)

    def _show_result(self, text: str) -> None:
        _output_set(self._output, text)
        self._status.set("Comparison complete")

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Runtime Entries ──────────────────────────────────────────────
class RuntimeEntriesPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Runtime PATH Entries",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        tk.Label(
            self,
            text="Entries injected at runtime (not from registry / rc files)",
            font=("Segoe UI", 10),
            fg=_CLR_DIM,
            bg=_CLR_BG,
        ).pack(pady=(0, 4))

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Scan", self._scan)

        self._tree = _make_tree(
            self,
            [
                ("status", "Source", 90),
                ("scope", "Scope", 70),
                ("path", "Path", 600),
            ],
        )
        self._output = _make_output(self, height=4)
        self._scan()

    def _scan(self) -> None:
        self._status.set("Scanning for runtime entries...")
        self._runner.run(self._fetch, on_success=self._display, on_error=self._on_error)

    @staticmethod
    def _fetch() -> list[tuple[str, str, str]]:
        from pathkeeper.services import detect_runtime_path_entries

        entries = detect_runtime_path_entries()
        return [
            (
                "persisted" if e.persisted else "runtime",
                e.scope.value if e.scope else "-",
                e.value,
            )
            for e in entries
        ]

    def _display(self, rows: list[tuple[str, str, str]]) -> None:
        for child in self._tree.get_children():
            self._tree.delete(child)
        runtime_count = 0
        for status, scope, path in rows:
            tag = "ok" if status == "persisted" else "warn"
            self._tree.insert("", tk.END, values=(status, scope, path), tags=(tag,))
            if status == "runtime":
                runtime_count += 1
        msg = (
            f"{runtime_count} runtime-only entry/entries detected"
            if runtime_count
            else "All entries match the persisted PATH"
        )
        _output_set(self._output, msg)
        self._status.set(msg)

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── Self-Check ────────────────────────────────────────────────────
class SelfCheckPanel(_BasePanel):
    def __init__(
        self, parent: tk.Misc, runner: _BackgroundRunner, status_var: tk.StringVar
    ) -> None:
        super().__init__(parent, runner, status_var)
        tk.Label(
            self,
            text="Self-Check",
            font=("Segoe UI", 14, "bold"),
            fg=_CLR_ACCENT,
            bg=_CLR_BG,
        ).pack(pady=(12, 4))
        tk.Label(
            self,
            text="Verify pathkeeper installation health",
            font=("Segoe UI", 10),
            fg=_CLR_DIM,
            bg=_CLR_BG,
        ).pack(pady=(0, 4))

        toolbar = _make_toolbar(self)
        _toolbar_btn(toolbar, "Run checks", self._run)

        self._tree = _make_tree(
            self,
            [
                ("status", "Status", 70),
                ("name", "Check", 200),
                ("detail", "Detail", 400),
                ("remediation", "Remediation", 420),
            ],
        )
        self._output = _make_output(self, height=4)
        self._run()

    def _run(self) -> None:
        self._status.set("Running self-checks...")
        self._runner.run(self._fetch, on_success=self._display, on_error=self._on_error)

    @staticmethod
    def _fetch() -> list[object]:
        from pathkeeper.core.selfcheck import run_selfcheck

        report = run_selfcheck()
        return list(report.checks)

    def _display(self, checks: list[object]) -> None:
        from pathkeeper.core.selfcheck import (
            _STATUS_FAIL,
            _STATUS_WARN,
            SelfCheckResult,
        )

        for child in self._tree.get_children():
            self._tree.delete(child)
        fail_count = 0
        warn_count = 0
        for check in checks:
            if not isinstance(check, SelfCheckResult):
                continue
            if check.status == _STATUS_FAIL:
                status_label = "FAIL"
                tag = "error"
                fail_count += 1
            elif check.status == _STATUS_WARN:
                status_label = "WARN"
                tag = "warn"
                warn_count += 1
            else:
                status_label = "PASS"
                tag = "ok"
            self._tree.insert(
                "",
                tk.END,
                values=(status_label, check.name, check.detail, check.remediation),
                tags=(tag,),
            )
        if fail_count:
            msg = f"{fail_count} check(s) failed, {warn_count} warning(s)"
        elif warn_count:
            msg = f"All checks passed with {warn_count} warning(s)"
        else:
            msg = "All checks passed"
        _output_set(self._output, msg)
        self._status.set(msg)

    def _on_error(self, exc: Exception) -> None:
        _output_set(self._output, f"Error: {exc}")
        self._status.set(f"Error: {exc}")


# ── entry point ───────────────────────────────────────────────────
def launch_gui() -> int:
    """Create and run the tkinter application.  Returns 0."""
    logger.info("Launching pathkeeper GUI.")
    app = PathkeeperApp()
    app.mainloop()
    logger.info("Pathkeeper GUI exited.")
    return 0


# Allow direct execution: python -m pathkeeper.gui.app
if __name__ == "__main__":
    raise SystemExit(launch_gui())
