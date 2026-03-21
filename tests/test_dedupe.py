from __future__ import annotations

from pathlib import Path

from pathkeeper.core.dedupe import dedupe_entries


def test_dedupe_entries_removes_duplicates_invalids_and_empty(tmp_path: Path) -> None:
    one = tmp_path / "one"
    one.mkdir()
    result = dedupe_entries(
        [str(one), "", str(one), str(tmp_path / "missing")],
        "linux",
        keep="first",
        remove_invalid=True,
    )
    assert result.cleaned == [str(one)]
    assert result.removed_empty == [""]
    assert result.removed_duplicates == [str(one)]
    assert result.removed_invalid == [str(tmp_path / "missing")]


def test_dedupe_entries_keep_last_preserves_latest_duplicate(tmp_path: Path) -> None:
    first = tmp_path / "alpha"
    second = tmp_path / "beta"
    first.mkdir()
    second.mkdir()
    result = dedupe_entries([str(first), str(second), str(first)], "linux", keep="last", remove_invalid=False)
    assert result.cleaned == [str(second), str(first)]

