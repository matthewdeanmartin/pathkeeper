"""Tests for `doctor --explain` and explain_entry()."""
from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig
from pathkeeper.core.diagnostics import explain_entry
from pathkeeper.models import DiagnosticEntry, Scope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(
    *,
    index: int = 1,
    value: str = "/usr/bin",
    scope: Scope = Scope.SYSTEM,
    exists: bool = True,
    is_dir: bool = True,
    is_duplicate: bool = False,
    duplicate_of: int | None = None,
    is_empty: bool = False,
    has_unexpanded_vars: bool = False,
    expanded_value: str = "/usr/bin",
) -> DiagnosticEntry:
    return DiagnosticEntry(
        index=index,
        value=value,
        scope=scope,
        exists=exists,
        is_dir=is_dir,
        is_duplicate=is_duplicate,
        duplicate_of=duplicate_of,
        is_empty=is_empty,
        has_unexpanded_vars=has_unexpanded_vars,
        expanded_value=expanded_value,
    )


class StubAdapter:
    def __init__(self, system: list[str], user: list[str]) -> None:
        self._system = system
        self._user = user

    def read_system_path(self) -> list[str]:
        return list(self._system)

    def read_user_path(self) -> list[str]:
        return list(self._user)

    def read_system_path_raw(self) -> str:
        return ":".join(self._system)

    def read_user_path_raw(self) -> str:
        return ":".join(self._user)


# ---------------------------------------------------------------------------
# Unit tests for explain_entry
# ---------------------------------------------------------------------------

def test_explain_entry_empty() -> None:
    entry = _make_entry(value="", is_empty=True, exists=False, is_dir=False, expanded_value="")
    explanation = explain_entry(entry, "linux")
    assert "empty" in explanation.lower()
    assert "pathkeeper dedupe" in explanation


def test_explain_entry_duplicate_references_original() -> None:
    entry = _make_entry(
        value="/usr/bin",
        is_duplicate=True,
        duplicate_of=1,
        index=3,
    )
    explanation = explain_entry(entry, "linux")
    assert "#1" in explanation
    assert "duplicate" in explanation.lower()
    assert "pathkeeper dedupe" in explanation


def test_explain_entry_missing_directory() -> None:
    entry = _make_entry(
        value="/opt/gone/bin",
        exists=False,
        is_dir=False,
        expanded_value="/opt/gone/bin",
    )
    explanation = explain_entry(entry, "linux")
    assert "does not exist" in explanation.lower()
    assert "/opt/gone/bin" in explanation
    assert "pathkeeper" in explanation


def test_explain_entry_file_not_directory(tmp_path: Path) -> None:
    f = tmp_path / "notadir.txt"
    f.write_text("x", encoding="utf-8")
    entry = _make_entry(
        value=str(f),
        exists=True,
        is_dir=False,
        expanded_value=str(f),
    )
    explanation = explain_entry(entry, "linux")
    assert "file" in explanation.lower()
    assert "directory" in explanation.lower()


def test_explain_entry_unexpanded_vars_windows() -> None:
    entry = _make_entry(
        value="%MYAPP%\\bin",
        has_unexpanded_vars=True,
        expanded_value="%MYAPP%\\bin",
    )
    explanation = explain_entry(entry, "windows")
    assert "variable" in explanation.lower() or "unexpanded" in explanation.lower()
    assert "%MYAPP%" in explanation


def test_explain_entry_unexpanded_vars_unix() -> None:
    entry = _make_entry(
        value="$MYAPP/bin",
        has_unexpanded_vars=True,
        expanded_value="$MYAPP/bin",
    )
    explanation = explain_entry(entry, "linux")
    assert "variable" in explanation.lower() or "unexpanded" in explanation.lower()
    assert "$MYAPP/bin" in explanation


def test_explain_entry_healthy_entry(tmp_path: Path) -> None:
    d = tmp_path / "tools"
    d.mkdir()
    entry = _make_entry(value=str(d), expanded_value=str(d))
    explanation = explain_entry(entry, "linux")
    assert "healthy" in explanation.lower()


# ---------------------------------------------------------------------------
# CLI integration tests for `doctor --explain`
# ---------------------------------------------------------------------------

def test_doctor_explain_shows_explanation_for_missing_entry(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/nonexistent/missing"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor", "--explain"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "does not exist" in output.lower() or "uninstalled" in output.lower() or "moved" in output.lower()


def test_doctor_explain_shows_explanation_for_duplicate(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/usr/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor", "--explain"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "duplicate" in output.lower()
    assert "#1" in output


def test_doctor_explain_not_shown_without_flag(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    """Without --explain, no per-entry explanation text should appear."""
    adapter = StubAdapter(system=["/usr/bin"], user=["/nonexistent/missing"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor"])
    output = capsys.readouterr().out
    assert exit_code == 0
    # The explanation for a missing dir should not appear in plain doctor output
    assert "does not exist" not in output.lower()


def test_inspect_explain_flag_not_accepted(capsys: CaptureFixture[str]) -> None:
    """inspect does not accept --explain (it's doctor-only)."""
    with pytest.raises(SystemExit) as exc:
        cli.run(["inspect", "--explain"])
    assert exc.value.code != 0


def test_doctor_explain_no_explanation_for_valid_entries(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    valid = tmp_path / "bin"
    valid.mkdir()
    adapter = StubAdapter(system=[str(valid)], user=[])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor", "--explain"])
    output = capsys.readouterr().out
    assert exit_code == 0
    # No explanation lines should appear under healthy entries
    assert "does not exist" not in output.lower()
    # "dup-of" is the per-entry duplicate indicator; "duplicates:" is just the summary count
    assert "dup-of" not in output.lower()
