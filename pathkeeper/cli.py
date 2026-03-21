from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence

from pathkeeper import __version__
from pathkeeper.config import backups_home, load_config
from pathkeeper.core.backup import create_backup, list_backups, prune_backups, resolve_backup
from pathkeeper.core.dedupe import dedupe_entries
from pathkeeper.core.diagnostics import analyze_snapshot, doctor_recommendations, join_path
from pathkeeper.core.diff import compute_diff, render_diff
from pathkeeper.core.edit import EditSession
from pathkeeper.core.path_reader import read_snapshot
from pathkeeper.core.path_writer import write_snapshot
from pathkeeper.core.populate import discover_tools, group_matches, load_catalog
from pathkeeper.core.schedule import install_schedule, remove_schedule, schedule_status
from pathkeeper.errors import PathkeeperError, UserCancelledError
from pathkeeper.interactive import MenuHandler, run_interactive
from pathkeeper.models import PathSnapshot, Scope
from pathkeeper.platform import get_platform_adapter, normalized_os_name


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pathkeeper", description="PATH backup, restore, and repair tool.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect PATH entries.")
    _add_diagnostic_flags(inspect_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose PATH problems.")
    _add_diagnostic_flags(doctor_parser)

    backup_parser = subparsers.add_parser("backup", help="Create a PATH backup.")
    backup_parser.add_argument("--note", default="", help="Attach a note to the backup.")
    backup_parser.add_argument("--tag", default="manual", choices=["manual", "auto"], help="Backup tag.")
    backup_parser.add_argument("--quiet", action="store_true", help="Suppress confirmation output.")

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


def _render_report(report: object) -> None:
    print(json.dumps(report, indent=2))


def _print_diagnostics(args: argparse.Namespace) -> int:
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    report = analyze_snapshot(
        system_entries=snapshot.system_path,
        user_entries=snapshot.user_path,
        os_name=normalized_os_name(),
        scope=scope,
        raw_value=snapshot.raw_for_scope(scope),
    )
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


def _backup_now(*, tag: str, note: str, quiet: bool) -> int:
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    destination = create_backup(snapshot, backup_dir=backups_home(), os_name=normalized_os_name(), tag=tag, note=note)
    prune_backups(backups_home(), config)
    if not quiet:
        print(f"Created backup: {destination}")
    return 0


def _snapshot_with_scope(snapshot: PathSnapshot, scope: Scope, entries: list[str], os_name: str) -> PathSnapshot:
    return snapshot.with_scope_entries(scope, entries, join_path(entries, os_name))


def _restore(args: argparse.Namespace) -> int:
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
    if config.restore.pre_backup and not args.no_pre_backup:
        _backup_now(tag="pre-restore", note=f"Before restore {target.source_file.name if target.source_file else args.identifier}", quiet=False)
    _confirm("Restore this PATH snapshot?", force=args.force)
    write_snapshot(adapter, target.snapshot, scope)
    print("Restore complete.")
    return 0


def _dedupe(args: argparse.Namespace) -> int:
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
        _backup_now(tag="pre-dedupe", note="Before dedupe", quiet=False)
        _confirm("Apply dedupe changes?", force=args.force)
        adapter.write_system_path(system_result.cleaned)
        adapter.write_user_path(user_result.cleaned)
        print("Dedupe complete.")
        return 0
    original = snapshot.entries_for_scope(scope)
    result = dedupe_entries(original, os_name, keep=args.keep, remove_invalid=args.remove_invalid)
    print(render_diff(compute_diff(result.original, result.cleaned, os_name)))
    if args.dry_run:
        return 0
    _backup_now(tag="pre-dedupe", note="Before dedupe", quiet=False)
    _confirm("Apply dedupe changes?", force=args.force)
    updated = _snapshot_with_scope(snapshot, scope, result.cleaned, os_name)
    write_snapshot(adapter, updated, scope)
    print("Dedupe complete.")
    return 0


def _populate(args: argparse.Namespace) -> int:
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
        print("No missing tool directories found.")
        return 0
    for category, items in group_matches(matches).items():
        print(category)
        for item in items:
            print(f"  - {item.path} ({item.name})")
    selected = matches if args.all else matches
    selected_paths = [item.path for item in selected]
    if args.dry_run:
        return 0
    _backup_now(tag="pre-populate", note="Before populate", quiet=False)
    _confirm("Add discovered entries?", force=args.force or args.all)
    original = snapshot.entries_for_scope(scope)
    updated = _snapshot_with_scope(snapshot, scope, [*original, *selected_paths], normalized_os_name())
    write_snapshot(adapter, updated, scope)
    print("Populate complete.")
    return 0


def _edit(args: argparse.Namespace) -> int:
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    session = EditSession(snapshot.entries_for_scope(scope), normalized_os_name())
    if args.add:
        session.add(args.add, args.position)
    if args.remove:
        session.delete(session.entries.index(args.remove))
    if args.move:
        if args.position is None:
            raise PathkeeperError("--move requires --position")
        session.move(session.entries.index(args.move), args.position)
    if args.replace_value:
        if args.new_path is None:
            raise PathkeeperError("--edit requires --new-path")
        session.replace(session.entries.index(args.replace_value), args.new_path)
    if not any([args.add, args.remove, args.move, args.replace_value]):
        print("Current entries:")
        for index, entry in enumerate(session.entries, start=1):
            print(f"{index:>3}. {entry}")
        return 0
    diff = session.diff()
    print(render_diff(diff))
    _backup_now(tag="pre-edit", note="Before edit", quiet=False)
    _confirm("Write edited PATH?", force=args.force)
    updated = _snapshot_with_scope(snapshot, scope, session.entries, normalized_os_name())
    write_snapshot(adapter, updated, scope)
    print("Edit complete.")
    return 0


def _schedule(args: argparse.Namespace) -> int:
    os_name = normalized_os_name()
    if args.schedule_command == "status":
        status = schedule_status(os_name)
        state = "enabled" if status.enabled else "disabled"
        print(f"Schedule is {state}: {status.detail}")
        return 0
    if args.schedule_command == "install":
        print(install_schedule(os_name, args.interval))
        return 0
    print(remove_schedule(os_name))
    return 0


def _interactive() -> int:
    parser = build_parser()
    backups = list_backups(backups_home())
    restore_handler: MenuHandler
    if backups and backups[0].source_file is not None:
        restore_namespace = parser.parse_args(["restore", backups[0].source_file.name])
        restore_handler = _restore
    else:
        restore_namespace = parser.parse_args(["inspect"])
        def restore_handler(_args: argparse.Namespace) -> int:
            print("No backups available yet.")
            return 0
    dispatch = {
        "1": ("Inspect", parser.parse_args(["inspect"]), _print_diagnostics),
        "2": ("Doctor", parser.parse_args(["doctor"]), _print_diagnostics),
        "3": ("Backup", parser.parse_args(["backup"]), lambda args: _backup_now(tag=args.tag, note=args.note, quiet=args.quiet)),
        "4": ("Restore", restore_namespace, restore_handler),
        "5": ("Dedupe", parser.parse_args(["dedupe"]), _dedupe),
        "6": ("Populate", parser.parse_args(["populate"]), _populate),
        "7": ("Edit", parser.parse_args(["edit"]), _edit),
        "8": ("Schedule status", parser.parse_args(["schedule", "status"]), _schedule),
    }
    return run_interactive(dispatch)


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command is None:
        return _interactive()
    if args.command in {"inspect", "doctor"}:
        return _print_diagnostics(args)
    if args.command == "backup":
        return _backup_now(tag=args.tag, note=args.note, quiet=args.quiet)
    if args.command == "restore":
        return _restore(args)
    if args.command == "dedupe":
        return _dedupe(args)
    if args.command == "populate":
        return _populate(args)
    if args.command == "edit":
        return _edit(args)
    if args.command == "schedule":
        return _schedule(args)
    raise PathkeeperError(f"Unknown command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        exit_code = run(argv)
    except PathkeeperError as error:
        print(error, file=sys.stderr)
        exit_code = error.exit_code
    if argv is None:
        raise SystemExit(exit_code)
    return exit_code
