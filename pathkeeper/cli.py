from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from pytable_formatter import Table  # type: ignore[import-untyped]

from pathkeeper import __version__
from pathkeeper.config import backups_home, load_config
from pathkeeper.core.backup import backup_content_hash, create_backup, list_backups, prune_backups, resolve_backup
from pathkeeper.core.dedupe import dedupe_entries
from pathkeeper.core.diagnostics import analyze_snapshot, doctor_recommendations, join_path
from pathkeeper.core.diff import compute_diff, render_diff
from pathkeeper.core.edit import EditSession
from pathkeeper.core.path_reader import read_snapshot
from pathkeeper.core.path_writer import PathWriter, write_changed_snapshot
from pathkeeper.core.populate import discover_tools, group_matches, load_catalog
from pathkeeper.core.repair_truncated import find_truncated_repairs
from pathkeeper.core.schedule import install_schedule, remove_schedule, schedule_status
from pathkeeper.errors import PathkeeperError, PermissionDeniedError, UserCancelledError
from pathkeeper.interactive import MenuEntry, MenuHandler, run_interactive
from pathkeeper.models import BackupRecord, DiagnosticReport, PathSnapshot, Scope, TruncatedPathRepair
from pathkeeper.platform import get_platform_adapter, normalized_os_name


LOG_LEVELS = {
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}
logger = logging.getLogger(__name__)


class _SystemWritableChecker(Protocol):
    def ensure_system_writable(self) -> None: ...


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pathkeeper", description="PATH backup, restore, and repair tool.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=sorted(LOG_LEVELS),
        help="Set logging verbosity.",
    )
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect PATH entries.")
    _add_diagnostic_flags(inspect_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose PATH problems.")
    _add_diagnostic_flags(doctor_parser)

    backup_parser = subparsers.add_parser("backup", help="Create a PATH backup.")
    backup_parser.add_argument("--note", default="", help="Attach a note to the backup.")
    backup_parser.add_argument("--tag", default="manual", choices=["manual", "auto"], help="Backup tag.")
    backup_parser.add_argument("--quiet", action="store_true", help="Suppress confirmation output.")
    backup_parser.add_argument("--force", action="store_true", help="Create a backup even if content is unchanged.")

    backups_parser = subparsers.add_parser("backups", help="List or inspect saved backups.")
    backups_subparsers = backups_parser.add_subparsers(dest="backups_command", required=True)
    list_backups_parser = backups_subparsers.add_parser("list", help="List available backups.")
    list_backups_parser.add_argument("--limit", type=int, default=20, help="Maximum number of backups to show.")
    show_backup_parser = backups_subparsers.add_parser("show", help="Show a backup snapshot.")
    show_backup_parser.add_argument("identifier", nargs="?", help="Backup file path or timestamp prefix. Defaults to latest.")

    restore_parser = subparsers.add_parser("restore", help="Restore a backup.")
    restore_parser.add_argument("identifier", help="Backup file path or timestamp prefix.")
    restore_parser.add_argument("--scope", default="all", choices=["system", "user", "all"])
    restore_parser.add_argument("--no-pre-backup", action="store_true")
    restore_parser.add_argument("--force", action="store_true")
    restore_parser.add_argument("--dry-run", action="store_true")

    dedupe_parser = subparsers.add_parser("dedupe", help="Remove duplicates and invalid entries.")
    dedupe_parser.add_argument("--scope", default="all", choices=["system", "user", "all"])
    dedupe_parser.add_argument("--keep", default="first", choices=["first", "last"])
    dedupe_parser.add_argument("--remove-invalid", dest="remove_invalid", action="store_true", default=True)
    dedupe_parser.add_argument("--no-remove-invalid", dest="remove_invalid", action="store_false")
    dedupe_parser.add_argument("--dry-run", action="store_true")
    dedupe_parser.add_argument("--force", action="store_true")

    populate_parser = subparsers.add_parser("populate", help="Discover common tool directories.")
    populate_parser.add_argument("--scope", default="user", choices=["system", "user"])
    populate_parser.add_argument("--all", action="store_true", help="Add all discovered paths.")
    populate_parser.add_argument("--category", default=None)
    populate_parser.add_argument("--dry-run", action="store_true")
    populate_parser.add_argument("--list-catalog", action="store_true")
    populate_parser.add_argument("--force", action="store_true")

    repair_truncated_parser = subparsers.add_parser(
        "repair-truncated",
        help="Repair likely truncated PATH entries.",
    )
    repair_truncated_parser.add_argument("--scope", default="all", choices=["system", "user", "all"])
    repair_truncated_parser.add_argument("--dry-run", action="store_true")
    repair_truncated_parser.add_argument("--force", action="store_true")

    edit_parser = subparsers.add_parser("edit", help="Edit PATH entries.")
    edit_parser.add_argument("--scope", default="user", choices=["system", "user"])
    edit_parser.add_argument("--add", default=None)
    edit_parser.add_argument("--remove", default=None)
    edit_parser.add_argument("--move", default=None)
    edit_parser.add_argument("--position", type=int, default=None)
    edit_parser.add_argument("--edit", dest="replace_value", default=None)
    edit_parser.add_argument("--new-path", default=None)
    edit_parser.add_argument("--force", action="store_true")

    schedule_parser = subparsers.add_parser("schedule", help="Install or inspect scheduled backups.")
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", required=True)
    install_parser = schedule_subparsers.add_parser("install", help="Install scheduled backups.")
    install_parser.add_argument("--interval", default="startup", help="startup or minute interval like 60m.")
    install_parser.add_argument("--trigger", default="startup", choices=["startup", "logon"])
    schedule_subparsers.add_parser("remove", help="Remove scheduled backups.")
    schedule_subparsers.add_parser("status", help="Inspect schedule status.")

    return parser


def _add_diagnostic_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", default="all", choices=["system", "user", "all"])
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--only-invalid", action="store_true")
    parser.add_argument("--only-dupes", action="store_true")


def _scope(value: str) -> Scope:
    return Scope.from_value(value)


def _confirm(message: str, *, force: bool) -> None:
    if force:
        return
    answer = input(f"{message} [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise UserCancelledError("User cancelled.")


def _prompt_yes_no(message: str, *, default: bool) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"{message} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def _prompt_scope(message: str, *, default: Scope = Scope.USER) -> Scope:
    while True:
        answer = input(f"{message} [system/user] (default {default.value}): ").strip().lower()
        if not answer:
            return default
        if answer in {"system", "user"}:
            return Scope.from_value(answer)
        print("Please enter 'system' or 'user'.")


def _render_report(report: object) -> None:
    print(json.dumps(report, indent=2))


def _configure_logging(level_name: str) -> None:
    logging.basicConfig(level=LOG_LEVELS[level_name], format="%(levelname)s: %(message)s", force=True)


def _print_diagnostics(args: argparse.Namespace) -> int:
    logger.info("Running %s for scope=%s", args.command, args.scope)
    scope = _scope(args.scope)
    _snapshot, report = _read_current_report(scope)
    if args.as_json:
        payload = {
            "summary": report.summary.__dict__,
            "entries": [entry.__dict__ | {"scope": entry.scope.value} for entry in report.entries],
            "path_length": report.path_length,
        }
        _render_report(payload)
        return 0
    entries = report.entries
    if args.only_invalid:
        entries = [entry for entry in entries if entry.value and (not entry.exists or not entry.is_dir)]
    if args.only_dupes:
        entries = [entry for entry in entries if entry.is_duplicate]
    for entry in entries:
        if entry.is_empty:
            marker = "!"
        elif entry.is_duplicate:
            marker = "D"
        elif not entry.exists:
            marker = "x"
        elif not entry.is_dir:
            marker = "~"
        else:
            marker = "ok"
        arrow = " -> var" if entry.has_unexpanded_vars else ""
        duplicate = f" dup-of #{entry.duplicate_of}" if entry.duplicate_of is not None else ""
        print(f"{entry.index:>3}. [{marker}] ({entry.scope.value}) {entry.value}{duplicate}{arrow}")
    print()
    print(
        f"Entries: {report.summary.total} | valid: {report.summary.valid} | invalid: {report.summary.invalid} | "
        f"duplicates: {report.summary.duplicates} | empty: {report.summary.empty}"
    )
    for warning in report.summary.warnings:
        print(f"Warning: {warning}")
    if args.command == "doctor":
        print()
        for recommendation in doctor_recommendations(report):
            print(f"- {recommendation}")
    return 0


def _backup_now(*, tag: str, note: str, quiet: bool, force: bool = False) -> int:
    logger.info("Running backup with tag=%s", tag)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    destination = create_backup(
        snapshot,
        backup_dir=backups_home(),
        os_name=normalized_os_name(),
        tag=tag,
        note=note,
        force=force,
    )
    if destination is None:
        return 0
    prune_backups(backups_home(), config)
    if not quiet:
        print(f"Created backup: {destination}")
    return 0


def _backup_command(args: argparse.Namespace) -> int:
    return _backup_now(tag=args.tag, note=args.note, quiet=args.quiet, force=args.force)


def _format_backup_timestamp_utc(value: datetime) -> str:
    timestamp = value.astimezone(UTC)
    return timestamp.strftime("%Y-%m-%d %H:%MZ")


def _recent_backups(*, limit: int = 20) -> list[BackupRecord]:
    return list_backups(backups_home())[:limit]


def _render_backup_listing(records: list[BackupRecord], *, numbered: bool) -> None:
    headers = ["Backup", "Timestamp", "Tag", "Hash", "Host", "OS", "System", "User", "Note"]
    if numbered:
        headers.insert(0, "#")
    rows: list[list[str]] = []
    for index, record in enumerate(records, start=1):
        row = [
            record.source_file.name if record.source_file is not None else "<unsaved>",
            _format_backup_timestamp_utc(record.timestamp),
            record.tag,
            backup_content_hash(record),
            record.hostname,
            record.os_name,
            str(len(record.system_path)),
            str(len(record.user_path)),
            record.note,
        ]
        if numbered:
            row.insert(0, str(index))
        rows.append(row)
    print(Table(headers=headers, data=rows, max_width=220).render())


def _read_current_report(scope: Scope) -> tuple[PathSnapshot, DiagnosticReport]:
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    report = analyze_snapshot(
        system_entries=snapshot.system_path,
        user_entries=snapshot.user_path,
        os_name=normalized_os_name(),
        scope=scope,
        raw_value=snapshot.raw_for_scope(scope),
    )
    return snapshot, report


def _print_interactive_startup_banner() -> None:
    backup_dir = backups_home()
    backup_count = len(list_backups(backup_dir))
    _snapshot, report = _read_current_report(Scope.ALL)
    print(f"Backups: {backup_dir} ({backup_count} saved)")
    print(
        "Inspect summary: "
        f"entries={report.summary.total} valid={report.summary.valid} invalid={report.summary.invalid} "
        f"duplicates={report.summary.duplicates} empty={report.summary.empty}"
    )
    for warning in report.summary.warnings:
        print(f"Warning: {warning}")
    print()


def _select_backup(identifier: str | None) -> tuple[BackupRecord, list[BackupRecord]]:
    records = list_backups(backups_home())
    if not records:
        raise PathkeeperError("No backups available.")
    if identifier:
        if identifier.isdigit():
            selection = int(identifier)
            recent = records[:20]
            if 1 <= selection <= len(recent):
                return recent[selection - 1], records
            raise PathkeeperError(f"Backup selection out of range: {identifier}")
        return resolve_backup(identifier, backups_home()), records
    return records[0], records


def _list_backup_records(_args: argparse.Namespace) -> int:
    limit = max(1, int(getattr(_args, "limit", 20)))
    records = _recent_backups(limit=limit)
    if not records:
        print("No backups available.")
        return 0
    print(f"Most recent backups (showing up to {limit}):")
    _render_backup_listing(records, numbered=True)
    return 0


def _show_backup(args: argparse.Namespace) -> int:
    if args.identifier is None:
        records = _recent_backups(limit=20)
        if not records:
            print("No backups available.")
            return 0
        print("Most recent backups:")
        _render_backup_listing(records, numbered=True)
        identifier = input("Select backup number to inspect (blank for 1): ").strip() or "1"
        args = argparse.Namespace(identifier=identifier)
    record, _records = _select_backup(args.identifier)
    name = record.source_file.name if record.source_file is not None else "<unsaved>"
    print(f"Backup: {name}")
    print(f"Timestamp: {_format_backup_timestamp_utc(record.timestamp)}")
    print(f"Tag: {record.tag}")
    print(f"Content hash: {backup_content_hash(record)}")
    print(f"Host: {record.hostname}")
    print(f"OS: {record.os_name}")
    print(f"Note: {record.note or '-'}")
    print()
    print("System PATH:")
    if record.system_path:
        for index, entry in enumerate(record.system_path, start=1):
            print(f"{index:>3}. {entry}")
    else:
        print("  <empty>")
    print()
    print("User PATH:")
    if record.user_path:
        for index, entry in enumerate(record.user_path, start=1):
            print(f"{index:>3}. {entry}")
    else:
        print("  <empty>")
    return 0


def _snapshot_with_scope(snapshot: PathSnapshot, scope: Scope, entries: list[str], os_name: str) -> PathSnapshot:
    return snapshot.with_scope_entries(scope, entries, join_path(entries, os_name))


def _entry_index(entries: list[str], value: str) -> int:
    try:
        return entries.index(value)
    except ValueError as error:
        raise PathkeeperError(f"Entry not found in PATH: {value}") from error


def _entry_number(value: str, entries: list[str]) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise PathkeeperError(f"Expected an entry number, got: {value}") from error
    index = number - 1
    if index < 0 or index >= len(entries):
        raise PathkeeperError(f"Entry number out of range: {number}")
    return index


def _position_number(value: str) -> int:
    try:
        position = int(value)
    except ValueError as error:
        raise PathkeeperError(f"Expected a position number, got: {value}") from error
    if position < 1:
        raise PathkeeperError("Positions start at 1.")
    return position - 1


def _render_edit_session(entries: list[str], *, scope: Scope, os_name: str) -> None:
    report = analyze_snapshot(
        system_entries=entries if scope is Scope.SYSTEM else [],
        user_entries=entries if scope is Scope.USER else [],
        os_name=os_name,
        scope=scope,
        raw_value=join_path(entries, os_name),
    )
    print(f"Editing {scope.value.upper()} PATH ({len(entries)} entries):")
    print()
    for entry in report.entries:
        if entry.is_duplicate and entry.duplicate_of is not None:
            marker = "D"
            detail = f"duplicate of #{entry.duplicate_of}"
        elif entry.is_empty:
            marker = "!"
            detail = "empty"
        elif not entry.exists:
            marker = "!"
            detail = "missing"
        elif not entry.is_dir:
            marker = "!"
            detail = "file"
        else:
            marker = "✓"
            detail = "ok"
        print(f"  {entry.index:>2}. {entry.value} [{marker} {detail}]")
    print()
    print("Commands:")
    print("  [a]dd <path> [position]  - Add an entry at the end or at a position")
    print("  [d]elete <n>             - Remove entry number n")
    print("  [m]ove <n> <pos>         - Move entry n to position pos")
    print("  [e]dit <n> <newpath>     - Replace entry number n")
    print("  [s]wap <n> <m>           - Swap two entries")
    print("  [u]ndo                   - Undo the last change")
    print("  [r]eset                  - Reset to the original PATH")
    print("  [p]review                - Show the staged diff")
    print("  [w]rite                  - Save changes")
    print("  [q]uit                   - Discard changes")
    print()


def _preflight_write(current: PathSnapshot, updated: PathSnapshot, scope: Scope, adapter: object) -> None:
    if scope not in {Scope.SYSTEM, Scope.ALL}:
        return
    if current.system_path == updated.system_path:
        return
    checker = getattr(adapter, "ensure_system_writable", None)
    if callable(checker):
        checker()


def _restore(args: argparse.Namespace) -> int:
    logger.info("Restoring PATH from backup %s with scope=%s", args.identifier, args.scope)
    config = load_config()
    adapter = get_platform_adapter(config)
    current = read_snapshot(adapter)
    target = resolve_backup(args.identifier, backups_home())
    scope = _scope(args.scope)
    before = current.entries_for_scope(scope)
    after = target.snapshot.entries_for_scope(scope)
    diff = compute_diff(before, after, normalized_os_name())
    print(render_diff(diff))
    if args.dry_run:
        return 0
    _preflight_write(current, target.snapshot, scope, adapter)
    if config.restore.pre_backup and not args.no_pre_backup:
        _backup_now(
            tag="pre-restore",
            note=f"Before restore {target.source_file.name if target.source_file else args.identifier}",
            quiet=False,
        )
    _confirm("Restore this PATH snapshot?", force=args.force)
    write_changed_snapshot(adapter, current, target.snapshot, scope)
    logger.info("Restore complete for scope=%s", args.scope)
    print("Restore complete.")
    return 0


def _dedupe(args: argparse.Namespace) -> int:
    logger.info("Deduping PATH with scope=%s keep=%s remove_invalid=%s", args.scope, args.keep, args.remove_invalid)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    os_name = normalized_os_name()
    if scope is Scope.ALL:
        system_result = dedupe_entries(snapshot.system_path, os_name, keep=args.keep, remove_invalid=args.remove_invalid)
        user_result = dedupe_entries(snapshot.user_path, os_name, keep=args.keep, remove_invalid=args.remove_invalid)
        system_diff = render_diff(compute_diff(system_result.original, system_result.cleaned, os_name))
        user_diff = render_diff(compute_diff(user_result.original, user_result.cleaned, os_name))
        print("System diff:")
        print(system_diff)
        print("\nUser diff:")
        print(user_diff)
        if args.dry_run:
            return 0
        updated = PathSnapshot(
            system_path=system_result.cleaned,
            user_path=user_result.cleaned,
            system_path_raw=join_path(system_result.cleaned, os_name),
            user_path_raw=join_path(user_result.cleaned, os_name),
        )
        _preflight_write(snapshot, updated, scope, adapter)
        _backup_now(tag="pre-dedupe", note="Before dedupe", quiet=False)
        _confirm("Apply dedupe changes?", force=args.force)
        write_changed_snapshot(adapter, snapshot, updated, scope)
        logger.info("Dedupe complete for scope=%s", args.scope)
        print("Dedupe complete.")
        return 0
    original = snapshot.entries_for_scope(scope)
    result = dedupe_entries(original, os_name, keep=args.keep, remove_invalid=args.remove_invalid)
    print(render_diff(compute_diff(result.original, result.cleaned, os_name)))
    if args.dry_run:
        return 0
    updated = _snapshot_with_scope(snapshot, scope, result.cleaned, os_name)
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-dedupe", note="Before dedupe", quiet=False)
    _confirm("Apply dedupe changes?", force=args.force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Dedupe complete for scope=%s", args.scope)
    print("Dedupe complete.")
    return 0


def _populate(args: argparse.Namespace) -> int:
    logger.info("Populating PATH for scope=%s category=%s", args.scope, args.category or "all")
    config = load_config()
    adapter = get_platform_adapter(config)
    if args.list_catalog:
        print((backups_home().parent / "known_tools.toml").read_text(encoding="utf-8"))
        return 0
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    catalog = load_catalog(config)
    existing = snapshot.entries_for_scope(Scope.ALL)
    matches = discover_tools(catalog, existing, os_name=normalized_os_name(), category=args.category)
    if not matches:
        logger.info("No populate matches found.")
        print("No missing tool directories found.")
        return 0
    logger.info("Found %s populate match(es).", len(matches))
    for category, items in group_matches(matches).items():
        print(category)
        for item in items:
            print(f"  - {item.path} ({item.name})")
    selected = matches if args.all else matches
    selected_paths = [item.path for item in selected]
    if args.dry_run:
        return 0
    updated = _snapshot_with_scope(snapshot, scope, [*snapshot.entries_for_scope(scope), *selected_paths], normalized_os_name())
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-populate", note="Before populate", quiet=False)
    _confirm("Add discovered entries?", force=args.force or args.all)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Populate complete for scope=%s", args.scope)
    print("Populate complete.")
    return 0


def _scope_has_dedupe_changes(entries: list[str], *, os_name: str, keep: str, remove_invalid: bool) -> bool:
    result = dedupe_entries(entries, os_name, keep=keep, remove_invalid=remove_invalid)
    return result.original != result.cleaned


def _prompt_choice(message: str, *, upper_bound: int) -> int | None:
    while True:
        answer = input(message).strip().lower()
        if answer in {"", "s", "skip"}:
            return None
        if answer.isdigit():
            selection = int(answer)
            if 1 <= selection <= upper_bound:
                return selection - 1
        print(f"Enter a number between 1 and {upper_bound}, or press Enter to skip.")


def _select_truncated_repairs(
    repairs: list[tuple[str, "TruncatedPathRepair"]],
    *,
    force: bool,
) -> list[tuple[str, "TruncatedPathRepair"]]:
    selected: list[tuple[str, TruncatedPathRepair]] = []
    for current_value, repair in repairs:
        print(f"[{repair.scope.value}] Entry #{repair.display_index}: {current_value}")
        if len(repair.candidates) == 1:
            candidate = repair.candidates[0]
            print(f"Suggested repair: {candidate.path} ({candidate.source})")
            if force or _prompt_yes_no("Apply this repair?", default=True):
                selected.append((candidate.path, repair))
            else:
                print("Skipped this repair.")
            print()
            continue
        print("Possible repairs:")
        for index, candidate in enumerate(repair.candidates, start=1):
            print(f"  {index}. {candidate.path} ({candidate.source})")
        choice = _prompt_choice("Choose a repair number (Enter to skip): ", upper_bound=len(repair.candidates))
        if choice is None:
            print("Skipped this repair.")
            print()
            continue
        selected.append((repair.candidates[choice].path, repair))
        print()
    return selected


def _repair_truncated(args: argparse.Namespace) -> int:
    logger.info("Repairing truncated PATH entries for scope=%s", args.scope)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    scope = _scope(args.scope)
    repairs = find_truncated_repairs(
        snapshot=snapshot,
        scope=scope,
        os_name=os_name,
        records=list_backups(backups_home()),
    )
    if not repairs:
        print("No likely truncated PATH entries were found.")
        return 0
    if args.dry_run:
        print("Possible truncated PATH repairs:")
        for repair in repairs:
            print(f"[{repair.scope.value}] Entry #{repair.display_index}: {repair.value}")
            for index, candidate in enumerate(repair.candidates, start=1):
                print(f"  {index}. {candidate.path} ({candidate.source})")
        return 0
    selections = _select_truncated_repairs([(repair.value, repair) for repair in repairs], force=args.force)
    if not selections:
        print("No truncated PATH repairs were selected.")
        return 0
    updated = PathSnapshot(
        system_path=list(snapshot.system_path),
        user_path=list(snapshot.user_path),
        system_path_raw=snapshot.system_path_raw,
        user_path_raw=snapshot.user_path_raw,
    )
    for replacement, repair in selections:
        if repair.scope is Scope.SYSTEM:
            updated.system_path[repair.scope_index] = replacement
            updated = PathSnapshot(
                system_path=updated.system_path,
                user_path=updated.user_path,
                system_path_raw=join_path(updated.system_path, os_name),
                user_path_raw=updated.user_path_raw,
            )
        else:
            updated.user_path[repair.scope_index] = replacement
            updated = PathSnapshot(
                system_path=updated.system_path,
                user_path=updated.user_path,
                system_path_raw=updated.system_path_raw,
                user_path_raw=join_path(updated.user_path, os_name),
            )
    if updated.system_path != snapshot.system_path:
        print("System diff:")
        print(render_diff(compute_diff(snapshot.system_path, updated.system_path, os_name)))
    if updated.user_path != snapshot.user_path:
        if updated.system_path != snapshot.system_path:
            print()
        print("User diff:")
        print(render_diff(compute_diff(snapshot.user_path, updated.user_path, os_name)))
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-repair-truncated", note="Before repairing truncated PATH entries", quiet=False)
    _confirm("Apply truncated PATH repairs?", force=args.force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Truncated PATH repair complete for scope=%s", args.scope)
    print("Truncated PATH repair complete.")
    return 0


def _interactive_dedupe(args: argparse.Namespace) -> int:
    try:
        return _dedupe(args)
    except PermissionDeniedError:
        if normalized_os_name() != "windows" or _scope(args.scope) is not Scope.ALL:
            raise
        config = load_config()
        adapter = get_platform_adapter(config)
        snapshot = read_snapshot(adapter)
        os_name = normalized_os_name()
        user_changes = _scope_has_dedupe_changes(
            snapshot.user_path,
            os_name=os_name,
            keep=args.keep,
            remove_invalid=args.remove_invalid,
        )
        if not user_changes:
            raise
        print("System PATH changes need an elevated shell, but user PATH changes can still be applied.")
        if not _prompt_yes_no("Restrict dedupe to the user PATH instead?", default=True):
            print("Dedupe was not changed.")
            return 0
        fallback_args = argparse.Namespace(
            command="dedupe",
            scope="user",
            keep=args.keep,
            remove_invalid=args.remove_invalid,
            dry_run=args.dry_run,
            force=args.force,
        )
        return _dedupe(fallback_args)


def _write_edit_session(
    *,
    adapter: PathWriter,
    args_force: bool,
    os_name: str,
    scope: Scope,
    session: EditSession,
    snapshot: PathSnapshot,
) -> int:
    diff = session.diff()
    print(render_diff(diff))
    if diff.added == [] and diff.removed == [] and diff.reordered == []:
        print("No staged changes to write.")
        return 0
    updated = _snapshot_with_scope(snapshot, scope, session.entries, os_name)
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-edit", note="Before edit", quiet=False)
    _confirm("Write edited PATH?", force=args_force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Edit complete for scope=%s", scope.value)
    print("Edit complete.")
    return 0


def _interactive_edit(args: argparse.Namespace) -> int:
    logger.info("Starting interactive edit session")
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    scope = _prompt_scope("Edit which PATH scope?", default=_scope(args.scope))
    session = EditSession(snapshot.entries_for_scope(scope), os_name)
    while True:
        _render_edit_session(session.entries, scope=scope, os_name=os_name)
        raw_command = input("edit> ").strip()
        if not raw_command:
            continue
        try:
            parts = shlex.split(raw_command)
        except ValueError as error:
            print(f"Invalid edit command: {error}")
            continue
        command = parts[0].lower()
        try:
            if command in {"a", "add"}:
                if len(parts) not in {2, 3}:
                    raise PathkeeperError("Usage: add <path> [position]")
                position = _position_number(parts[2]) if len(parts) == 3 else None
                session.add(parts[1], position)
                print("Added staged entry.")
                continue
            if command in {"d", "delete"}:
                if len(parts) != 2:
                    raise PathkeeperError("Usage: delete <n>")
                session.delete(_entry_number(parts[1], session.entries))
                print("Deleted staged entry.")
                continue
            if command in {"m", "move"}:
                if len(parts) != 3:
                    raise PathkeeperError("Usage: move <n> <position>")
                session.move(_entry_number(parts[1], session.entries), _position_number(parts[2]))
                print("Moved staged entry.")
                continue
            if command in {"e", "edit", "replace"}:
                if len(parts) != 3:
                    raise PathkeeperError("Usage: edit <n> <newpath>")
                session.replace(_entry_number(parts[1], session.entries), parts[2])
                print("Replaced staged entry.")
                continue
            if command in {"s", "swap"}:
                if len(parts) != 3:
                    raise PathkeeperError("Usage: swap <n> <m>")
                session.swap(_entry_number(parts[1], session.entries), _entry_number(parts[2], session.entries))
                print("Swapped staged entries.")
                continue
            if command in {"u", "undo"}:
                if session.undo():
                    print("Undid the last staged change.")
                else:
                    print("Nothing to undo.")
                continue
            if command in {"r", "reset"}:
                session.reset()
                print("Reset staged changes.")
                continue
            if command in {"p", "preview"}:
                print(render_diff(session.diff()))
                continue
            if command in {"w", "write"}:
                return _write_edit_session(
                    adapter=adapter,
                    args_force=False,
                    os_name=os_name,
                    scope=scope,
                    session=session,
                    snapshot=snapshot,
                )
            if command in {"q", "quit"}:
                print("Discarded staged edit changes.")
                return 0
            print("Unknown edit command.")
        except PathkeeperError as error:
            print(error)


def _edit(args: argparse.Namespace) -> int:
    logger.info("Editing PATH for scope=%s", args.scope)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    os_name = normalized_os_name()
    if not any([args.add, args.remove, args.move, args.replace_value]):
        return _interactive_edit(args)
    session = EditSession(snapshot.entries_for_scope(scope), os_name)
    if args.add:
        session.add(args.add, args.position)
    if args.remove:
        session.delete(_entry_index(session.entries, args.remove))
    if args.move:
        if args.position is None:
            raise PathkeeperError("--move requires --position")
        session.move(_entry_index(session.entries, args.move), args.position)
    if args.replace_value:
        if args.new_path is None:
            raise PathkeeperError("--edit requires --new-path")
        session.replace(_entry_index(session.entries, args.replace_value), args.new_path)
    return _write_edit_session(
        adapter=adapter,
        args_force=args.force,
        os_name=os_name,
        scope=scope,
        session=session,
        snapshot=snapshot,
    )


def _schedule(args: argparse.Namespace) -> int:
    os_name = normalized_os_name()
    if args.schedule_command == "status":
        status = schedule_status(os_name)
        if status.enabled:
            logger.info("Schedule is enabled: %s", status.detail)
            print(f"Schedule is enabled: {status.detail}")
        else:
            logger.warning("Schedule is disabled.")
            print("Schedule is disabled. Run `pathkeeper schedule install` to enable automatic backups.")
        return 0
    if args.schedule_command == "install":
        trigger = getattr(args, "trigger", "startup")
        logger.info("Installing schedule with interval=%s trigger=%s", args.interval, trigger)
        print(install_schedule(os_name, args.interval, trigger=trigger))
        return 0
    logger.info("Removing schedule.")
    print(remove_schedule(os_name))
    return 0


def _interactive_schedule_status(args: argparse.Namespace) -> int:
    os_name = normalized_os_name()
    status = schedule_status(os_name)
    if status.enabled:
        print(f"Schedule is enabled: {status.detail}")
        return 0
    print("Scheduled backups are not set up yet.")
    if not _prompt_yes_no("Install automatic backups now?", default=True):
        print("Scheduled backups were not changed.")
        return 0
    install_args = argparse.Namespace(schedule_command="install", interval="startup", trigger="startup", command="schedule")
    try:
        return _schedule(install_args)
    except PermissionDeniedError:
        if os_name != "windows":
            raise
        print("Installing a startup task on Windows needs an elevated shell.")
        if not _prompt_yes_no("Install a per-user logon backup task instead?", default=True):
            print("Scheduled backups were not changed.")
            return 0
        fallback_args = argparse.Namespace(schedule_command="install", interval="startup", trigger="logon", command="schedule")
        try:
            return _schedule(fallback_args)
        except PermissionDeniedError:
            print("Windows denied creation of the per-user logon task too.")
            print("Run pathkeeper from an elevated shell to install the startup task, or ask your administrator if Task Scheduler is blocked.")
            return 0


def _interactive() -> int:
    parser = build_parser()
    restore_handler: MenuHandler
    def list_backups_handler(_args: argparse.Namespace) -> int:
        return _list_backup_records(parser.parse_args(["backups", "list"]))

    def show_backup_handler(_args: argparse.Namespace) -> int:
        return _show_backup(parser.parse_args(["backups", "show"]))

    backups = list_backups(backups_home())
    if backups and backups[0].source_file is not None:
        restore_namespace = parser.parse_args(["restore", backups[0].source_file.name])
        restore_handler = _restore
    else:
        restore_namespace = parser.parse_args(["inspect"])

        def restore_handler(_args: argparse.Namespace) -> int:
            print("No backups available yet.")
            return 0
    dispatch = {
        "1": MenuEntry("Inspect", "Review PATH entries and their health", parser.parse_args(["inspect"]), _print_diagnostics),
        "2": MenuEntry("Doctor", "Diagnose problems and suggest repairs", parser.parse_args(["doctor"]), _print_diagnostics),
        "3": MenuEntry("Create backup", "Save the current PATH snapshot", parser.parse_args(["backup"]), _backup_command),
        "4": MenuEntry("List backups", "Browse recent backups and hashes", parser.parse_args(["backups", "list"]), list_backups_handler),
        "5": MenuEntry("Show backup", "Inspect one backup in detail", parser.parse_args(["backups", "show"]), show_backup_handler),
        "6": MenuEntry("Restore", "Restore the most recent backup", restore_namespace, restore_handler),
        "7": MenuEntry("Dedupe", "Remove duplicates and broken entries", parser.parse_args(["dedupe"]), _interactive_dedupe),
        "8": MenuEntry("Populate", "Discover common tool directories", parser.parse_args(["populate"]), _populate),
        "9": MenuEntry("Edit", "Stage PATH changes in an editor", parser.parse_args(["edit"]), _edit),
        "10": MenuEntry("Repair truncated", "Repair entries missing leading path segments", parser.parse_args(["repair-truncated"]), _repair_truncated),
        "11": MenuEntry("Schedule status", "Check or install automatic backups", parser.parse_args(["schedule", "status"]), _interactive_schedule_status),
    }
    _print_interactive_startup_banner()
    return run_interactive(dispatch)


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.log_level)
    if args.command is None:
        return _interactive()
    if args.command in {"inspect", "doctor"}:
        return _print_diagnostics(args)
    if args.command == "backup":
        return _backup_command(args)
    if args.command == "backups":
        if args.backups_command == "list":
            return _list_backup_records(args)
        if args.backups_command == "show":
            return _show_backup(args)
    if args.command == "restore":
        return _restore(args)
    if args.command == "dedupe":
        return _dedupe(args)
    if args.command == "populate":
        return _populate(args)
    if args.command == "repair-truncated":
        return _repair_truncated(args)
    if args.command == "edit":
        return _edit(args)
    if args.command == "schedule":
        return _schedule(args)
    raise PathkeeperError(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        exit_code = run(argv)
    except PathkeeperError as error:
        if isinstance(error, UserCancelledError):
            logger.warning("%s", error)
        else:
            logger.error("%s", error)
        exit_code = error.exit_code
    if argv is None:
        raise SystemExit(exit_code)
    return exit_code
