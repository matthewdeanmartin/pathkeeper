"""Tests for compute_diff / render_diff and the 'pathkeeper diff' CLI subcommand."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig
from pathkeeper.core.diff import compute_diff, render_diff
from pathkeeper.models import BackupRecord, PathDiff

# ---------------------------------------------------------------------------
# Helpers shared with test_cli.py (duplicated to keep tests self-contained)
# ---------------------------------------------------------------------------


def _write_backup(
    path: Path,
    *,
    timestamp: str,
    tag: str,
    note: str = "",
    system_path: list[str] | None = None,
    user_path: list[str] | None = None,
    os_name: str = "linux",
) -> None:
    record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        hostname="host",
        os_name=os_name,
        tag=tag,
        note=note,
        system_path=system_path or ["/usr/bin"],
        user_path=user_path or ["/home/user/bin"],
        system_path_raw=":".join(system_path or ["/usr/bin"]),
        user_path_raw=":".join(user_path or ["/home/user/bin"]),
    )
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit tests for compute_diff
# ---------------------------------------------------------------------------


def test_compute_diff_detects_added_entry() -> None:
    diff = compute_diff(["/usr/bin"], ["/usr/bin", "/opt/tools/bin"], "linux")
    assert "/opt/tools/bin" in diff.added
    assert diff.removed == []
    assert diff.reordered == []


def test_compute_diff_detects_removed_entry() -> None:
    diff = compute_diff(["/usr/bin", "/opt/tools/bin"], ["/usr/bin"], "linux")
    assert "/opt/tools/bin" in diff.removed
    assert diff.added == []
    assert diff.reordered == []


def test_compute_diff_detects_reordered_entry() -> None:
    diff = compute_diff(
        ["/usr/bin", "/usr/local/bin"], ["/usr/local/bin", "/usr/bin"], "linux"
    )
    assert diff.added == []
    assert diff.removed == []
    assert len(diff.reordered) == 2  # both entries moved


def test_compute_diff_identical_paths_returns_no_changes() -> None:
    paths = ["/usr/bin", "/usr/local/bin", "/home/user/.cargo/bin"]
    diff = compute_diff(paths, paths, "linux")
    assert diff == PathDiff(added=[], removed=[], reordered=[])


def test_compute_diff_empty_to_populated() -> None:
    diff = compute_diff([], ["/usr/bin", "/usr/local/bin"], "linux")
    assert set(diff.added) == {"/usr/bin", "/usr/local/bin"}
    assert diff.removed == []


def test_compute_diff_populated_to_empty() -> None:
    diff = compute_diff(["/usr/bin", "/usr/local/bin"], [], "linux")
    assert set(diff.removed) == {"/usr/bin", "/usr/local/bin"}
    assert diff.added == []


def test_compute_diff_windows_case_insensitive() -> None:
    # Same path, different case — should be treated as identical on Windows
    diff = compute_diff(
        ["C:\\Windows\\System32"],
        ["c:\\windows\\system32"],
        "windows",
    )
    assert diff == PathDiff(added=[], removed=[], reordered=[])


def test_compute_diff_linux_case_sensitive() -> None:
    # Different case on Linux = different entries
    diff = compute_diff(["/Usr/bin"], ["/usr/bin"], "linux")
    assert "/usr/bin" in diff.added
    assert "/Usr/bin" in diff.removed


def test_compute_diff_windows_trailing_backslash_normalized() -> None:
    # Trailing backslash should be stripped and still match
    diff = compute_diff(
        ["C:\\Windows\\System32\\"], ["C:\\Windows\\System32"], "windows"
    )
    assert diff == PathDiff(added=[], removed=[], reordered=[])


# ---------------------------------------------------------------------------
# Unit tests for render_diff
# ---------------------------------------------------------------------------


def test_render_diff_shows_added_section() -> None:
    diff = PathDiff(added=["/new/bin"], removed=[], reordered=[])
    output = render_diff(diff)
    assert "Added:" in output
    assert "+ /new/bin" in output


def test_render_diff_shows_removed_section() -> None:
    diff = PathDiff(added=[], removed=["/old/bin"], reordered=[])
    output = render_diff(diff)
    assert "Removed:" in output
    assert "- /old/bin" in output


def test_render_diff_shows_reordered_section() -> None:
    diff = PathDiff(added=[], removed=[], reordered=["/usr/bin"])
    output = render_diff(diff)
    assert "Reordered:" in output
    assert "~ /usr/bin" in output


def test_render_diff_no_changes_message() -> None:
    diff = PathDiff(added=[], removed=[], reordered=[])
    assert render_diff(diff) == "No changes."


def test_render_diff_all_sections_present() -> None:
    diff = PathDiff(added=["/new"], removed=["/old"], reordered=["/moved"])
    output = render_diff(diff)
    assert "Added:" in output
    assert "Removed:" in output
    assert "Reordered:" in output
    # Sections appear in the right order
    assert (
        output.index("Added:") < output.index("Removed:") < output.index("Reordered:")
    )


# ---------------------------------------------------------------------------
# CLI integration tests for `pathkeeper diff`
# ---------------------------------------------------------------------------


def test_diff_by_number_shows_no_changes_for_identical_backups(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "1", "2"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No changes." in output


def test_diff_detects_added_user_path_entry(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        user_path=["/home/user/bin"],
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
        user_path=["/home/user/bin", "/opt/new-tool/bin"],
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "2", "1"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "User PATH:" in output
    assert "/opt/new-tool/bin" in output


def test_diff_detects_removed_system_path_entry(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        system_path=["/usr/bin", "/opt/old-sdk/bin"],
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
        system_path=["/usr/bin"],
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "2", "1"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "System PATH:" in output
    assert "/opt/old-sdk/bin" in output


def test_diff_scope_user_only_skips_system_section(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        system_path=["/usr/bin", "/extra"],
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "1", "2", "--scope", "user"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "System PATH:" not in output
    assert "User PATH:" in output


def test_diff_scope_system_only_skips_user_section(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "1", "2", "--scope", "system"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "User PATH:" not in output
    assert "System PATH:" in output


def test_diff_header_contains_both_backup_names(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["diff", "1", "2"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "2025-03-02T10-00-00_manual.json" in output
    assert "2025-03-01T10-00-00_manual.json" in output


def test_diff_raises_when_no_backups_exist(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.main(["diff", "1", "2"])
    assert exit_code != 0
    assert "No backups available." in capsys.readouterr().err


def test_diff_out_of_range_number_raises(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.main(["diff", "1", "5"])
    assert exit_code != 0
    assert "out of range" in capsys.readouterr().err.lower()


def test_diff_by_filename(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
        user_path=["/home/user/bin"],
    )
    _write_backup(
        tmp_path / "2025-03-02T10-00-00_manual.json",
        timestamp="2025-03-02T10:00:00Z",
        tag="manual",
        user_path=["/home/user/bin", "/new/tool"],
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(
        [
            "diff",
            "2025-03-01T10-00-00_manual.json",
            "2025-03-02T10-00-00_manual.json",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "/new/tool" in output
