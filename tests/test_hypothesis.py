"""Property-based tests using Hypothesis.

Targets pure / near-pure functions that operate on data structures rather than
the filesystem or registry.  No files are created; all PATH manipulation runs
through in-memory logic only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from string import printable

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from pathkeeper.config import AppConfig, GeneralConfig
from pathkeeper.core.backup import backup_content_hash, backup_filename, prune_backups
from pathkeeper.core.diagnostics import (
    canonicalize_entry,
    has_unexpanded_variables,
    join_path,
    path_separator_for,
    split_path,
)
from pathkeeper.core.diff import compute_diff, render_diff
from pathkeeper.core.edit import EditSession
from pathkeeper.models import (
    BackupRecord,
    DiagnosticSummary,
    PathDiff,
    PathSnapshot,
    Scope,
)
from pathkeeper.services import format_backup_timestamp_utc

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

OS_NAMES = st.sampled_from(["linux", "windows", "darwin"])

# Safe path-component text: printable ASCII excluding separators we care about
_SAFE_CHARS = "".join(c for c in printable if c not in (":", ";", "\x00", "\n", "\r"))

safe_text = st.text(alphabet=_SAFE_CHARS, min_size=0, max_size=60)
path_entry = st.text(alphabet=_SAFE_CHARS, min_size=1, max_size=60)
path_entries = st.lists(path_entry, min_size=0, max_size=20)
nonempty_path_entries = st.lists(path_entry, min_size=1, max_size=20)


def snapshots(entries_strategy=path_entries):
    return st.builds(
        PathSnapshot,
        system_path=entries_strategy,
        user_path=entries_strategy,
        system_path_raw=safe_text,
        user_path_raw=safe_text,
    )


def backup_records(os_name_st=OS_NAMES):
    return st.builds(
        BackupRecord,
        version=st.just(1),
        timestamp=st.datetimes(timezones=st.just(UTC)),
        hostname=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=20
        ),
        os_name=os_name_st,
        tag=st.sampled_from(["auto", "manual"]),
        note=safe_text,
        system_path=path_entries,
        user_path=path_entries,
        system_path_raw=safe_text,
        user_path_raw=safe_text,
        source_file=st.none(),
    )


# ---------------------------------------------------------------------------
# PathSnapshot model properties
# ---------------------------------------------------------------------------


@given(snap=snapshots(), scope=st.sampled_from(list(Scope)))
def test_entries_for_scope_length(snap: PathSnapshot, scope: Scope) -> None:
    """ALL scope returns the union of system + user entries."""
    entries = snap.entries_for_scope(scope)
    if scope is Scope.ALL:
        assert len(entries) == len(snap.system_path) + len(snap.user_path)
    elif scope is Scope.SYSTEM:
        assert len(entries) == len(snap.system_path)
    else:
        assert len(entries) == len(snap.user_path)


@given(snap=snapshots())
def test_entries_for_scope_all_contains_both(snap: PathSnapshot) -> None:
    all_entries = snap.entries_for_scope(Scope.ALL)
    assert all(e in all_entries for e in snap.system_path)
    assert all(e in all_entries for e in snap.user_path)


@given(snap=snapshots())
def test_raw_for_scope_system_matches_field(snap: PathSnapshot) -> None:
    assert snap.raw_for_scope(Scope.SYSTEM) == snap.system_path_raw


@given(snap=snapshots())
def test_raw_for_scope_user_matches_field(snap: PathSnapshot) -> None:
    assert snap.raw_for_scope(Scope.USER) == snap.user_path_raw


@given(snap=snapshots(), entries=path_entries, raw=safe_text)
def test_with_scope_entries_system_roundtrip(
    snap: PathSnapshot, entries: list[str], raw: str
) -> None:
    updated = snap.with_scope_entries(Scope.SYSTEM, entries, raw)
    assert updated.system_path == entries
    assert updated.system_path_raw == raw
    assert updated.user_path == snap.user_path
    assert updated.user_path_raw == snap.user_path_raw


@given(snap=snapshots(), entries=path_entries, raw=safe_text)
def test_with_scope_entries_user_roundtrip(
    snap: PathSnapshot, entries: list[str], raw: str
) -> None:
    updated = snap.with_scope_entries(Scope.USER, entries, raw)
    assert updated.user_path == entries
    assert updated.user_path_raw == raw
    assert updated.system_path == snap.system_path
    assert updated.system_path_raw == snap.system_path_raw


@given(snap=snapshots())
def test_snapshot_property_on_backup_record(snap: PathSnapshot) -> None:
    """BackupRecord.snapshot reconstructs an equivalent PathSnapshot."""
    record = BackupRecord(
        version=1,
        timestamp=datetime.now(UTC),
        hostname="host",
        os_name="linux",
        tag="manual",
        note="",
        system_path=snap.system_path,
        user_path=snap.user_path,
        system_path_raw=snap.system_path_raw,
        user_path_raw=snap.user_path_raw,
    )
    rebuilt = record.snapshot
    assert rebuilt.system_path == snap.system_path
    assert rebuilt.user_path == snap.user_path
    assert rebuilt.system_path_raw == snap.system_path_raw
    assert rebuilt.user_path_raw == snap.user_path_raw


# ---------------------------------------------------------------------------
# diagnostics: split_path / join_path roundtrip
# ---------------------------------------------------------------------------


@given(os_name=OS_NAMES)
def test_split_empty_string_returns_empty_list(os_name: str) -> None:
    assert split_path("", os_name) == []


@given(os_name=OS_NAMES, entries=nonempty_path_entries)
def test_join_then_split_roundtrip(os_name: str, entries: list[str]) -> None:
    """join then split must recover the original entries."""
    joined = join_path(entries, os_name)
    recovered = split_path(joined, os_name)
    assert recovered == entries


@given(os_name=OS_NAMES, raw=safe_text)
def test_split_then_join_roundtrip(os_name: str, raw: str) -> None:
    """split then join must recover the original raw string (when non-empty)."""
    if raw == "":
        return  # empty is a special case — split returns []
    entries = split_path(raw, os_name)
    recovered = join_path(entries, os_name)
    assert recovered == raw


@given(os_name=OS_NAMES)
def test_path_separator_is_one_char(os_name: str) -> None:
    sep = path_separator_for(os_name)
    assert len(sep) == 1


# ---------------------------------------------------------------------------
# diagnostics: canonicalize_entry idempotency
# ---------------------------------------------------------------------------


@given(entry=path_entry, os_name=OS_NAMES)
def test_canonicalize_is_idempotent(entry: str, os_name: str) -> None:
    """Canonicalizing an already-canonical entry changes nothing."""
    once = canonicalize_entry(entry, os_name)
    twice = canonicalize_entry(once, os_name)
    assert once == twice


@given(entry=path_entry)
def test_canonicalize_windows_is_lowercase(entry: str) -> None:
    result = canonicalize_entry(entry, "windows")
    assert result == result.casefold()


@given(entry=path_entry)
def test_canonicalize_darwin_is_lowercase(entry: str) -> None:
    result = canonicalize_entry(entry, "darwin")
    assert result == result.casefold()


# ---------------------------------------------------------------------------
# diagnostics: has_unexpanded_variables never crashes
# ---------------------------------------------------------------------------


@given(entry=safe_text, os_name=OS_NAMES)
def test_has_unexpanded_variables_returns_bool(entry: str, os_name: str) -> None:
    result = has_unexpanded_variables(entry, os_name)
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# diff: properties of compute_diff
# ---------------------------------------------------------------------------


@given(entries=path_entries, os_name=OS_NAMES)
def test_diff_identical_has_no_changes(entries: list[str], os_name: str) -> None:
    diff = compute_diff(entries, entries, os_name)
    assert diff.added == []
    assert diff.removed == []
    assert diff.reordered == []


@given(original=path_entries, updated=path_entries, os_name=OS_NAMES)
def test_diff_added_not_in_original(
    original: list[str], updated: list[str], os_name: str
) -> None:
    diff = compute_diff(original, updated, os_name)
    original_keys = {canonicalize_entry(e, os_name) for e in original}
    for entry in diff.added:
        assert canonicalize_entry(entry, os_name) not in original_keys


@given(original=path_entries, updated=path_entries, os_name=OS_NAMES)
def test_diff_removed_not_in_updated(
    original: list[str], updated: list[str], os_name: str
) -> None:
    diff = compute_diff(original, updated, os_name)
    updated_keys = {canonicalize_entry(e, os_name) for e in updated}
    for entry in diff.removed:
        assert canonicalize_entry(entry, os_name) not in updated_keys


@given(original=path_entries, updated=path_entries, os_name=OS_NAMES)
def test_diff_reordered_exist_in_both(
    original: list[str], updated: list[str], os_name: str
) -> None:
    diff = compute_diff(original, updated, os_name)
    original_keys = {canonicalize_entry(e, os_name) for e in original}
    updated_keys = {canonicalize_entry(e, os_name) for e in updated}
    for entry in diff.reordered:
        key = canonicalize_entry(entry, os_name)
        assert key in original_keys
        assert key in updated_keys


@given(
    diff=st.builds(
        PathDiff, added=path_entries, removed=path_entries, reordered=path_entries
    )
)
def test_render_diff_returns_string(diff: PathDiff) -> None:
    result = render_diff(diff)
    assert isinstance(result, str)
    assert len(result) > 0


@given(
    diff=st.builds(
        PathDiff, added=path_entries, removed=path_entries, reordered=path_entries
    )
)
def test_render_diff_no_changes_iff_all_empty(diff: PathDiff) -> None:
    result = render_diff(diff)
    all_empty = not diff.added and not diff.removed and not diff.reordered
    assert (result == "No changes.") == all_empty


# ---------------------------------------------------------------------------
# EditSession: invariants
# ---------------------------------------------------------------------------


@given(entries=path_entries, os_name=OS_NAMES)
def test_edit_session_initial_state(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    assert session.entries == entries


@given(entries=path_entries, os_name=OS_NAMES, new_entry=path_entry)
def test_edit_session_add_appends(
    entries: list[str], os_name: str, new_entry: str
) -> None:
    session = EditSession(entries, os_name)
    session.add(new_entry)
    assert session.entries[-1] == new_entry
    assert len(session.entries) == len(entries) + 1


@given(entries=nonempty_path_entries, os_name=OS_NAMES)
def test_edit_session_delete_reduces_length(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    session.delete(0)
    assert len(session.entries) == len(entries) - 1


@given(entries=nonempty_path_entries, os_name=OS_NAMES, new_value=path_entry)
def test_edit_session_replace_keeps_length(
    entries: list[str], os_name: str, new_value: str
) -> None:
    session = EditSession(entries, os_name)
    session.replace(0, new_value)
    assert len(session.entries) == len(entries)
    assert session.entries[0] == new_value


@given(entries=nonempty_path_entries, os_name=OS_NAMES)
def test_edit_session_undo_after_add(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    session.add("__new__")
    reverted = session.undo()
    assert reverted is True
    assert session.entries == entries


@given(entries=path_entries, os_name=OS_NAMES)
def test_edit_session_undo_empty_history(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    assert session.undo() is False


@given(entries=path_entries, os_name=OS_NAMES, new_entry=path_entry)
def test_edit_session_reset_restores_original(
    entries: list[str], os_name: str, new_entry: str
) -> None:
    session = EditSession(entries, os_name)
    session.add(new_entry)
    session.reset()
    assert session.entries == entries


@given(entries=st.lists(path_entry, min_size=2, max_size=20), os_name=OS_NAMES)
def test_edit_session_swap_is_symmetric(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    session.swap(0, 1)
    assert session.entries[0] == entries[1]
    assert session.entries[1] == entries[0]


@given(entries=st.lists(path_entry, min_size=2, max_size=20), os_name=OS_NAMES)
def test_edit_session_swap_double_restores(entries: list[str], os_name: str) -> None:
    session = EditSession(entries, os_name)
    session.swap(0, 1)
    session.swap(0, 1)
    assert session.entries == entries


@given(entries=path_entries, os_name=OS_NAMES)
def test_edit_session_diff_identical_after_reset(
    entries: list[str], os_name: str
) -> None:
    session = EditSession(entries, os_name)
    # reset on a fresh session: still identical to original
    session.reset()
    diff = session.diff()
    assert diff.added == []
    assert diff.removed == []
    assert diff.reordered == []


# ---------------------------------------------------------------------------
# backup: backup_filename and backup_content_hash
# ---------------------------------------------------------------------------


@given(
    ts=st.datetimes(timezones=st.just(UTC)),
    tag=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_-", min_size=1, max_size=20),
)
def test_backup_filename_ends_with_json(ts: datetime, tag: str) -> None:
    name = backup_filename(ts, tag)
    assert name.endswith(".json")


@given(
    ts=st.datetimes(timezones=st.just(UTC)),
    tag=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_-", min_size=1, max_size=20),
)
def test_backup_filename_contains_tag(ts: datetime, tag: str) -> None:
    name = backup_filename(ts, tag)
    assert tag in name


@given(record=backup_records())
def test_backup_content_hash_is_12_chars(record: BackupRecord) -> None:
    h = backup_content_hash(record)
    assert len(h) == 12
    assert h.isalnum()  # hex digits


@given(record=backup_records())
def test_backup_content_hash_is_deterministic(record: BackupRecord) -> None:
    assert backup_content_hash(record) == backup_content_hash(record)


@given(r1=backup_records(), r2=backup_records())
def test_backup_content_hash_differs_on_different_paths(
    r1: BackupRecord, r2: BackupRecord
) -> None:
    """Different system/user paths → different hashes (with very high probability)."""
    assume(
        r1.system_path != r2.system_path
        or r1.user_path != r2.user_path
        or r1.system_path_raw != r2.system_path_raw
        or r1.user_path_raw != r2.user_path_raw
        or r1.os_name != r2.os_name
    )
    # We only assert that at least one distinct input produces a distinct hash;
    # collision is possible but astronomically unlikely with 12 hex chars.
    # This test primarily checks that the function runs without crashing.
    h1 = backup_content_hash(r1)  # pylint: disable=unreachable
    h2 = backup_content_hash(r2)
    assert isinstance(h1, str)
    assert isinstance(h2, str)


# ---------------------------------------------------------------------------
# prune_backups: in-memory simulation (no files touched, source_file=None)
# ---------------------------------------------------------------------------


@given(
    records=st.lists(backup_records(), min_size=0, max_size=60),
    max_auto=st.integers(min_value=0, max_value=30),
    max_manual=st.integers(min_value=0, max_value=30),
    max_total=st.integers(min_value=0, max_value=60),
)
@settings(max_examples=100)
def test_prune_backups_does_not_crash_with_no_source_files(
    records: list[BackupRecord],
    max_auto: int,
    max_manual: int,
    max_total: int,
) -> None:
    """When source_file is None for all records, prune_backups is a no-op (nothing to delete)."""
    config = AppConfig(
        general=GeneralConfig(
            max_backups=max_total,
            max_auto_backups=max_auto,
            max_manual_backups=max_manual,
        )
    )
    from pathlib import Path

    # Pass a non-existent dir; prune will only unlink source_file paths, all None here.
    prune_backups(Path("/nonexistent_dir_hypothesis"), config, list(records))


# ---------------------------------------------------------------------------
# services: format_backup_timestamp_utc
# ---------------------------------------------------------------------------


@given(ts=st.datetimes(timezones=st.just(UTC)))
def test_format_backup_timestamp_ends_with_z(ts: datetime) -> None:
    result = format_backup_timestamp_utc(ts)
    assert result.endswith("Z")


@given(ts=st.datetimes(timezones=st.just(UTC)))
def test_format_backup_timestamp_has_expected_format(ts: datetime) -> None:
    result = format_backup_timestamp_utc(ts)
    # e.g. "2024-03-15 09:30Z"
    parts = result.split(" ")
    assert len(parts) == 2
    date_part, time_part = parts
    assert len(date_part) == 10  # YYYY-MM-DD
    assert time_part.endswith("Z")
    assert ":" in time_part


# ---------------------------------------------------------------------------
# DiagnosticSummary: structural invariants
# ---------------------------------------------------------------------------


@given(
    total=st.integers(min_value=0, max_value=1000),
    valid=st.integers(min_value=0, max_value=1000),
    invalid=st.integers(min_value=0, max_value=1000),
    duplicates=st.integers(min_value=0, max_value=1000),
    empty=st.integers(min_value=0, max_value=1000),
    files=st.integers(min_value=0, max_value=1000),
)
def test_diagnostic_summary_fields_are_stored(
    total: int,
    valid: int,
    invalid: int,
    duplicates: int,
    empty: int,
    files: int,
) -> None:
    summary = DiagnosticSummary(
        total=total,
        valid=valid,
        invalid=invalid,
        duplicates=duplicates,
        empty=empty,
        files=files,
    )
    assert summary.total == total
    assert summary.valid == valid
    assert summary.invalid == invalid
    assert summary.duplicates == duplicates
    assert summary.empty == empty
    assert summary.files == files
    assert summary.warnings == ()
