from __future__ import annotations

from pathlib import Path

from pathkeeper.core.diagnostics import analyze_snapshot
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
