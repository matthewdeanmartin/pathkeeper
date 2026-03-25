from __future__ import annotations

from pathlib import Path

import pytest

from pathkeeper.core.diagnostics import (
    _looks_like_missing_separator,
    analyze_snapshot,
    doctor_checks,
    expand_entry,
    explain_entry,
)
from pathkeeper.models import Scope


def test_analyze_snapshot_detects_duplicates_invalids_and_files(tmp_path: Path) -> None:
    valid_dir = tmp_path / "valid"
    valid_dir.mkdir()
    file_entry = tmp_path / "not-a-dir.txt"
    file_entry.write_text("x", encoding="utf-8")
    report = analyze_snapshot(
        system_entries=[
            str(valid_dir),
            str(valid_dir),
            str(file_entry),
            "$UNEXPANDED_TEST/tool",
            "",
        ],
        user_entries=[],
        os_name="linux",
        scope=Scope.SYSTEM,
        raw_value=":".join(
            [
                str(valid_dir),
                str(valid_dir),
                str(file_entry),
                "$UNEXPANDED_TEST/tool",
                "",
            ]
        ),
    )
    assert report.summary.total == 5
    assert report.summary.duplicates == 1
    assert report.summary.invalid >= 2
    assert report.summary.empty == 1
    assert any(entry.has_unexpanded_vars for entry in report.entries)


# ---------------------------------------------------------------------------
# Missing separator detection
# ---------------------------------------------------------------------------


def test_looks_like_missing_separator_unix_colon() -> None:
    # A literal colon inside a Unix PATH entry means the separator wasn't split
    assert _looks_like_missing_separator("/c/foo:/c/bar", "linux") is True


def test_looks_like_missing_separator_unix_normal_path() -> None:
    # A normal deep path should NOT trigger
    assert _looks_like_missing_separator("/usr/local/bin", "linux") is False


def test_looks_like_missing_separator_windows_mid_drive() -> None:
    # A drive letter appearing mid-string on Windows
    assert (
        _looks_like_missing_separator(r"C:\Windows\System32C:\Program Files", "windows")
        is True
    )


def test_looks_like_missing_separator_windows_normal() -> None:
    assert _looks_like_missing_separator(r"C:\Windows\System32", "windows") is False


def test_looks_like_missing_separator_empty() -> None:
    assert _looks_like_missing_separator("", "linux") is False


def test_looks_like_missing_separator_short() -> None:
    assert _looks_like_missing_separator("/c", "linux") is False


def test_analyze_snapshot_flags_missing_separator() -> None:
    report = analyze_snapshot(
        system_entries=["/c/foo:/c/bar"],
        user_entries=[],
        os_name="linux",
        scope=Scope.SYSTEM,
        raw_value="/c/foo:/c/bar",
    )
    assert report.summary.missing_separators == 1
    flagged = [e for e in report.entries if e.likely_missing_separator]
    assert len(flagged) == 1
    assert flagged[0].value == "/c/foo:/c/bar"


def test_analyze_snapshot_double_separator_is_empty_not_missing_sep() -> None:
    # :: produces an empty entry, not a missing-separator entry
    report = analyze_snapshot(
        system_entries=["/c/foo", "", "/c/baz"],
        user_entries=[],
        os_name="linux",
        scope=Scope.SYSTEM,
        raw_value="/c/foo::/c/baz",
    )
    assert report.summary.empty == 1
    assert report.summary.missing_separators == 0


def test_explain_entry_missing_separator() -> None:
    report = analyze_snapshot(
        system_entries=["/c/foo:/c/bar"],
        user_entries=[],
        os_name="linux",
        scope=Scope.SYSTEM,
        raw_value="/c/foo:/c/bar",
    )
    entry = report.entries[0]
    explanation = explain_entry(entry, "linux")
    assert "glued together" in explanation
    assert "separator" in explanation


def test_windows_embedded_semicolon() -> None:
    assert _looks_like_missing_separator(r"C:\foo;C:\bar", "windows") is True


def test_expand_entry_windows_vars_are_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.setenv("SYSTEMROOT", r"C:\WINDOWS")

    assert expand_entry(r"%SYSTEMROOT%\System32", "windows") == r"C:\WINDOWS\System32"
    assert expand_entry(r"%SystemRoot%\System32", "windows") == r"C:\WINDOWS\System32"


def test_doctor_ignores_resolved_windows_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.setenv("SYSTEMROOT", r"C:\WINDOWS")

    report = analyze_snapshot(
        system_entries=[r"%SYSTEMROOT%\System32", r"%SystemRoot%\System32"],
        user_entries=[],
        os_name="windows",
        scope=Scope.SYSTEM,
        raw_value=r"%SYSTEMROOT%\System32;%SystemRoot%\System32",
    )

    assert all(not entry.has_unexpanded_vars for entry in report.entries)
    unresolvable = next(
        check
        for check in doctor_checks(report)
        if check.name == "Unresolvable variables"
    )
    assert unresolvable.status == "pass"
