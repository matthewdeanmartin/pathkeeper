# PYTHON_ARGCOMPLETE_OK
from __future__ import annotations

import argparse
import logging
import tomllib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast

from pathkeeper import __version__
from pathkeeper.config import backups_home, load_config
from pathkeeper.core.backup import (
    _load_latest_backup,
    backup_content_hash,
    backup_filename,
    create_backup,
    list_backups,
    prune_backups,
    resolve_backup,
)
from pathkeeper.core.path_reader import read_snapshot
from pathkeeper.errors import PathkeeperError, PermissionDeniedError, UserCancelledError
from pathkeeper.models import Scope
from pathkeeper.platform import get_platform_adapter, normalized_os_name
from pathkeeper.theme import t

if TYPE_CHECKING:
    from pathkeeper.core.edit import EditSession
    from pathkeeper.core.path_writer import PathWriter
    from pathkeeper.interactive import MenuHandler
    from pathkeeper.models import (
        BackupRecord,
        DiagnosticReport,
        PathSnapshot,
        PopulateMatch,
        TruncatedPathRepair,
    )


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
    formatter_class: type[argparse.HelpFormatter] = argparse.HelpFormatter
    _totalhelp_action: type | None = None
    try:
        from rich_argparse import RichHelpFormatter as _Formatter

        formatter_class = _Formatter
        try:
            import totalhelp as _totalhelp

            totalhelp_action = getattr(_totalhelp, "TotalHelpAction", None)
            if totalhelp_action is not None:
                _totalhelp_action = cast(type[argparse.Action], totalhelp_action)
        except ImportError:
            pass
    except ImportError:
        pass
    _EPILOG = """
examples:
  # Diagnose your PATH
  pathkeeper doctor
  pathkeeper doctor --explain
  pathkeeper inspect --only-invalid

  # Back up and restore
  pathkeeper backup --note "before installing toolchain"
  pathkeeper backups list
  pathkeeper diff-current          # compare latest backup vs live PATH
  pathkeeper diff-current 2        # compare backup #2 vs live PATH
  pathkeeper restore 2025-03-05    # restore by timestamp prefix
  pathkeeper restore 2 --dry-run   # preview restore from backup #2

  # Clean up PATH
  pathkeeper dedupe --dry-run
  pathkeeper dedupe
  pathkeeper repair-truncated
  pathkeeper split-long --dry-run

  # Discover and add tools
  pathkeeper populate --dry-run
  pathkeeper populate

  # Inspect shadows and runtime additions
  pathkeeper shadow
  pathkeeper runtime-entries

  # Automate backups
  pathkeeper schedule install
  pathkeeper shell-startup

  # Verify your installation
  pathkeeper selfcheck
"""
    parser = argparse.ArgumentParser(
        prog="pathkeeper",
        description="PATH backup, restore, and repair tool.",
        formatter_class=formatter_class,
        epilog=_EPILOG,
    )
    if _totalhelp_action is not None:
        parser.add_argument(
            "--all-help",
            action=_totalhelp_action,
            help="Show help for all subcommands.",
        )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=sorted(LOG_LEVELS),
        help="Set logging verbosity.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        dest="no_color",
        default=False,
        help="Disable colored output.",
    )
    subparsers = parser.add_subparsers(dest="command")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect PATH entries.")
    _add_diagnostic_flags(inspect_parser)

    doctor_parser = subparsers.add_parser("doctor", help="Diagnose PATH problems.")
    _add_diagnostic_flags(doctor_parser)
    doctor_parser.add_argument(
        "--explain",
        action="store_true",
        help="Add plain-language explanation for each finding.",
    )

    backup_parser = subparsers.add_parser("backup", help="Create a PATH backup.")
    backup_parser.add_argument(
        "--note", default="", help="Attach a note to the backup."
    )
    backup_parser.add_argument(
        "--tag", default="manual", choices=["manual", "auto"], help="Backup tag."
    )
    backup_parser.add_argument(
        "--quiet", action="store_true", help="Suppress confirmation output."
    )
    backup_parser.add_argument(
        "--force",
        action="store_true",
        help="Create a backup even if content is unchanged.",
    )
    backup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview backup behavior without writing.",
    )

    backups_parser = subparsers.add_parser(
        "backups", help="List or inspect saved backups."
    )
    backups_subparsers = backups_parser.add_subparsers(
        dest="backups_command", required=True
    )
    list_backups_parser = backups_subparsers.add_parser(
        "list", help="List available backups."
    )
    list_backups_parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of backups to show."
    )
    show_backup_parser = backups_subparsers.add_parser(
        "show", help="Show a backup snapshot."
    )
    show_backup_parser.add_argument(
        "identifier",
        nargs="?",
        help="Backup file path or timestamp prefix. Defaults to latest.",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore a backup.")
    restore_parser.add_argument(
        "identifier", help="Backup file path or timestamp prefix."
    )
    restore_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )
    restore_parser.add_argument("--no-pre-backup", action="store_true")
    restore_parser.add_argument("--force", action="store_true")
    restore_parser.add_argument("--dry-run", action="store_true")

    dedupe_parser = subparsers.add_parser(
        "dedupe", help="Remove duplicates and invalid entries."
    )
    dedupe_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )
    dedupe_parser.add_argument("--keep", default="first", choices=["first", "last"])
    dedupe_parser.add_argument(
        "--remove-invalid", dest="remove_invalid", action="store_true", default=True
    )
    dedupe_parser.add_argument(
        "--no-remove-invalid", dest="remove_invalid", action="store_false"
    )
    dedupe_parser.add_argument("--dry-run", action="store_true")
    dedupe_parser.add_argument("--force", action="store_true")

    populate_parser = subparsers.add_parser(
        "populate", help="Discover common tool directories."
    )
    populate_parser.add_argument("--scope", default="user", choices=["system", "user"])
    populate_parser.add_argument(
        "--all", action="store_true", help="Add all discovered paths."
    )
    populate_parser.add_argument("--category", default=None)
    populate_parser.add_argument("--dry-run", action="store_true")
    populate_parser.add_argument("--list-catalog", action="store_true")
    populate_parser.add_argument("--force", action="store_true")

    repair_truncated_parser = subparsers.add_parser(
        "repair-truncated",
        help="Repair likely truncated PATH entries.",
    )
    repair_truncated_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )
    repair_truncated_parser.add_argument("--dry-run", action="store_true")
    repair_truncated_parser.add_argument("--force", action="store_true")

    split_long_parser = subparsers.add_parser(
        "split-long",
        help="Split a long Windows PATH into helper variables.",
    )
    split_long_parser.add_argument(
        "--scope", default="user", choices=["system", "user"]
    )
    split_long_parser.add_argument(
        "--max-length",
        type=int,
        default=2047,
        help="Target maximum length for the PATH value itself.",
    )
    split_long_parser.add_argument(
        "--chunk-length",
        type=int,
        default=2047,
        help="Maximum length for each helper variable value.",
    )
    split_long_parser.add_argument(
        "--var-prefix",
        default=None,
        help="Prefix for generated helper variables (default depends on scope).",
    )
    split_long_parser.add_argument("--dry-run", action="store_true")
    split_long_parser.add_argument("--force", action="store_true")

    edit_parser = subparsers.add_parser("edit", help="Edit PATH entries.")
    edit_parser.add_argument("--scope", default="user", choices=["system", "user"])
    edit_parser.add_argument("--add", default=None)
    edit_parser.add_argument("--remove", default=None)
    edit_parser.add_argument("--move", default=None)
    edit_parser.add_argument("--position", type=int, default=None)
    edit_parser.add_argument("--edit", dest="replace_value", default=None)
    edit_parser.add_argument("--new-path", default=None)
    edit_parser.add_argument("--force", action="store_true")
    edit_parser.add_argument("--dry-run", action="store_true")

    schedule_parser = subparsers.add_parser(
        "schedule", help="Install or inspect scheduled backups."
    )
    schedule_subparsers = schedule_parser.add_subparsers(
        dest="schedule_command", required=True
    )
    install_parser = schedule_subparsers.add_parser(
        "install", help="Install scheduled backups."
    )
    install_parser.add_argument(
        "--interval", default="startup", help="startup or minute interval like 60m."
    )
    install_parser.add_argument(
        "--trigger", default="startup", choices=["startup", "logon"]
    )
    install_parser.add_argument("--dry-run", action="store_true")
    remove_parser = schedule_subparsers.add_parser(
        "remove", help="Remove scheduled backups."
    )
    remove_parser.add_argument("--dry-run", action="store_true")
    schedule_subparsers.add_parser("status", help="Inspect schedule status.")

    diff_parser = subparsers.add_parser(
        "diff", help="Show differences between two backups."
    )
    diff_parser.add_argument(
        "backup_a", help="First backup: file path, timestamp prefix, or number."
    )
    diff_parser.add_argument(
        "backup_b", help="Second backup: file path, timestamp prefix, or number."
    )
    diff_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )

    shadow_parser = subparsers.add_parser(
        "shadow",
        help="Show executables that shadow each other across PATH directories.",
    )
    shadow_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )
    shadow_parser.add_argument("--json", action="store_true", dest="as_json")

    diff_current_parser = subparsers.add_parser(
        "diff-current",
        help="Show differences between a backup and the current live PATH.",
    )
    diff_current_parser.add_argument(
        "identifier",
        nargs="?",
        help="Backup file path, timestamp prefix, or number. Defaults to latest.",
    )
    diff_current_parser.add_argument(
        "--scope", default="all", choices=["system", "user", "all"]
    )

    subparsers.add_parser(
        "runtime-entries",
        help="Show PATH entries injected at runtime (not from registry / rc files).",
    )

    shell_startup_parser = subparsers.add_parser(
        "shell-startup",
        help="Inject 'pathkeeper backup' into a shell startup file (Git Bash, WSL, PowerShell profile, etc.).",
    )
    shell_startup_parser.add_argument(
        "--shell",
        default=None,
        choices=["bash", "zsh", "powershell", "pwsh", "fish"],
        help="Target shell.  Auto-detected when omitted.",
    )
    shell_startup_parser.add_argument(
        "--rc-file",
        default=None,
        dest="rc_file",
        help="Override the startup file path.",
    )
    shell_startup_parser.add_argument("--dry-run", action="store_true")
    shell_startup_parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove the injected line instead of adding it.",
    )

    subparsers.add_parser(
        "selfcheck",
        help="Verify pathkeeper installation (backup dir, catalog, adapter, auto-backup).",
    )

    subparsers.add_parser("gui", help="Launch the graphical interface.")

    parser.add_argument(
        "--gui",
        action="store_true",
        default=False,
        help="Launch the graphical interface.",
    )

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
        answer = (
            input(f"{message} [system/user] (default {default.value}): ")
            .strip()
            .lower()
        )
        if not answer:
            return default
        if answer in {"system", "user"}:
            return Scope.from_value(answer)
        print("Please enter 'system' or 'user'.")


def _render_report(report: object) -> None:
    import json

    print(json.dumps(report, indent=2))


def _configure_logging(level_name: str) -> None:
    logging.basicConfig(
        level=LOG_LEVELS[level_name], format="%(levelname)s: %(message)s", force=True
    )


def _init_theme(args: argparse.Namespace) -> None:
    if getattr(args, "no_color", False):
        t.disable()
        return
    try:
        config = load_config()
        t.apply_config(config.display.color)
    except (OSError, ValueError, TypeError, tomllib.TOMLDecodeError) as exc:
        logger.warning("Could not load display config; using defaults: %s", exc)


def _print_inspect(args: argparse.Namespace) -> int:

    logger.info("Running inspect for scope=%s", args.scope)
    scope = _scope(args.scope)
    _snapshot, report = _read_current_report(scope)
    if args.as_json:
        payload = {
            "summary": report.summary.__dict__,
            "entries": [
                entry.__dict__ | {"scope": entry.scope.value}
                for entry in report.entries
            ],
            "path_length": report.path_length,
        }
        _render_report(payload)
        return 0
    entries = report.entries
    if args.only_invalid:
        entries = [
            entry
            for entry in entries
            if entry.value and (not entry.exists or not entry.is_dir)
        ]
    if args.only_dupes:
        entries = [entry for entry in entries if entry.is_duplicate]
    for entry in entries:
        if entry.is_empty:
            raw_marker = "!"
            is_ok = False
            is_warn = False
        elif entry.is_duplicate:
            raw_marker = "D"
            is_ok = False
            is_warn = True
        elif entry.likely_missing_separator:
            raw_marker = "!!"
            is_ok = False
            is_warn = True
        elif not entry.exists:
            raw_marker = "x"
            is_ok = False
            is_warn = False
        elif not entry.is_dir:
            raw_marker = "~"
            is_ok = False
            is_warn = False
        else:
            raw_marker = "ok"
            is_ok = True
            is_warn = False
        arrow = t.dim(" -> var") if entry.has_unexpanded_vars else ""
        duplicate = (
            t.warn(f" dup-of #{entry.duplicate_of}")
            if entry.duplicate_of is not None
            else ""
        )
        colored_marker = t.marker(f"[{raw_marker}]", ok=is_ok, warn=is_warn)
        colored_value = t.path_entry(
            entry.value,
            exists=entry.exists,
            duplicate=entry.is_duplicate,
            empty=entry.is_empty,
            is_file=entry.exists and not entry.is_dir,
        )
        scope_label = t.dim(f"({entry.scope.value})")
        exe_hint = ""
        if entry.executables and entry.is_dir and not entry.is_duplicate:
            names = ", ".join(entry.executables[:8])
            suffix = ", …" if len(entry.executables) > 8 else ""
            exe_hint = t.dim(f"  [{names}{suffix}]")
        print(
            f"{t.dim(f'{entry.index:>3}.')} {colored_marker} {scope_label} {colored_value}{duplicate}{arrow}{exe_hint}"
        )
    print()
    summary = (
        f"Entries: {report.summary.total}  "
        f"valid: {t.ok(str(report.summary.valid))}  "
        f"invalid: {t.error(str(report.summary.invalid)) if report.summary.invalid else t.dim('0')}  "
        f"duplicates: {t.warn(str(report.summary.duplicates)) if report.summary.duplicates else t.dim('0')}  "
        f"empty: {t.warn(str(report.summary.empty)) if report.summary.empty else t.dim('0')}"
    )
    print(summary)
    for warning in report.summary.warnings:
        print(t.warn(f"Warning: {warning}"))
    return 0


def _print_doctor(args: argparse.Namespace) -> int:
    from pathkeeper.core.diagnostics import (
        _STATUS_FAIL,
        _STATUS_WARN,
        doctor_checks,
        explain_entry,
    )

    logger.info("Running doctor for scope=%s", args.scope)
    scope = _scope(args.scope)
    _snapshot, report = _read_current_report(scope)
    verbose = getattr(args, "explain", False)
    if args.as_json:
        checks = doctor_checks(report)
        payload = {
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "detail": c.detail,
                    "affected": [
                        {"index": e.index, "value": e.value, "scope": e.scope.value}
                        for e in c.affected
                    ],
                    "remediation": c.remediation,
                }
                for c in checks
            ],
            "summary": report.summary.__dict__,
            "path_length": report.path_length,
        }
        _render_report(payload)
        return 0
    print(
        t.header("  PATH Health Check")
        + t.dim(f"  ({report.summary.total} entries, scope: {scope.value})")
    )
    print()
    checks = doctor_checks(report)
    issue_count = 0
    for check in checks:
        if check.status == _STATUS_FAIL:
            marker = t.error("FAIL")
            issue_count += len(check.affected) if check.affected else 1
        elif check.status == _STATUS_WARN:
            marker = t.warn("WARN")
            issue_count += len(check.affected) if check.affected else 1
        else:
            marker = t.ok("PASS")
        # Pad the check name for alignment
        padded_name = check.name.ljust(36, ".")
        print(f"  {marker}  {padded_name} {check.detail}")
        if check.affected and check.status != "pass":
            limit = None if verbose else 5
            shown = check.affected[:limit]
            for entry in shown:
                scope_label = t.dim(f"({entry.scope.value})")
                value_str = t.path_entry(
                    entry.value,
                    exists=entry.exists,
                    duplicate=entry.is_duplicate,
                    empty=entry.is_empty,
                    is_file=entry.exists and not entry.is_dir,
                )
                dup_hint = (
                    t.warn(f" dup-of #{entry.duplicate_of}")
                    if entry.duplicate_of is not None
                    else ""
                )
                print(
                    f"          {t.dim(f'#{entry.index}')} {scope_label} {value_str}{dup_hint}"
                )
                if verbose:
                    explanation = explain_entry(entry, report.os_name)
                    print(f"          {t.dim(explanation)}")
            remaining = len(check.affected) - len(shown)
            if remaining > 0:
                print(
                    t.dim(
                        f"          ... and {remaining} more (use --explain to see all)"
                    )
                )
        if check.remediation and check.status != "pass":
            print(f"          {t.accent('->')} {check.remediation}")
        if check.status != "pass":
            print()
    print()
    if issue_count == 0:
        print(t.ok("  Overall: healthy"))
    else:
        label = "issue" if issue_count == 1 else "issues"
        print(t.warn(f"  Overall: needs attention ({issue_count} {label})"))
    return 0


def _backup_now(*, tag: str, note: str, quiet: bool, force: bool = False) -> int:
    logger.info("Running backup with tag=%s", tag)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    backup_dir = backups_home()
    destination, all_records = create_backup(
        snapshot,
        backup_dir=backup_dir,
        os_name=normalized_os_name(),
        tag=tag,
        note=note,
        force=force,
    )
    if destination is None:
        return 0
    prune_backups(backup_dir, config, all_records)
    if not quiet:
        print(t.ok(f"Created backup: {destination}"))
    return 0


def _backup_command(args: argparse.Namespace) -> int:
    if args.dry_run:
        config = load_config()
        adapter = get_platform_adapter(config)
        snapshot = read_snapshot(adapter)
        latest = _load_latest_backup(backups_home())
        if (
            not args.force
            and latest is not None
            and latest.snapshot == snapshot
            and latest.os_name == normalized_os_name()
        ):
            print(
                t.dry_run(
                    "Dry run: backup would be skipped because the current PATH matches the latest saved backup."
                )
            )
            return 0
        preview_name = backup_filename(datetime.now(UTC), args.tag)
        print(
            t.dry_run(
                f"Dry run: would create backup at {backups_home() / preview_name}"
            )
        )
        if args.note:
            print(t.dry_run(f"Note: {args.note}"))
        return 0
    return _backup_now(tag=args.tag, note=args.note, quiet=args.quiet, force=args.force)


def _format_backup_timestamp_utc(value: datetime) -> str:
    timestamp = value.astimezone(UTC)
    return timestamp.strftime("%Y-%m-%d %H:%MZ")


def _recent_backups(*, limit: int = 20) -> list[BackupRecord]:
    return list_backups(backups_home())[:limit]


def _render_backup_listing(records: list[BackupRecord], *, numbered: bool) -> None:
    from pytable_formatter import Cell, Table

    headers: list[str | Cell] = [
        "Backup",
        "Timestamp",
        "Tag",
        "Hash",
        "Host",
        "OS",
        "System",
        "User",
        "Note",
    ]
    if numbered:
        headers.insert(0, "#")
    rows: list[list[object | Cell]] = []
    for index, record in enumerate(records, start=1):
        row: list[object | Cell] = [
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
    from pathkeeper.core.diagnostics import analyze_snapshot

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
    s = report.summary
    health = (
        t.ok("healthy")
        if s.invalid == 0 and s.duplicates == 0 and s.empty == 0
        else t.warn("needs attention")
    )
    print(t.header("pathkeeper") + t.dim(f"  {backup_count} backup(s) in {backup_dir}"))
    parts = [
        f"entries={s.total}",
        t.ok(f"valid={s.valid}"),
        (t.error if s.invalid else t.dim)(f"invalid={s.invalid}"),
        (t.warn if s.duplicates else t.dim)(f"dup={s.duplicates}"),
        (t.warn if s.empty else t.dim)(f"empty={s.empty}"),
    ]
    print(t.dim("PATH  ") + "  ".join(parts) + "  " + health)
    for warning in s.warnings:
        print(t.warn(f"  ! {warning}"))
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
        identifier = (
            input("Select backup number to inspect (blank for 1): ").strip() or "1"
        )
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


def _snapshot_with_scope(
    snapshot: PathSnapshot, scope: Scope, entries: list[str], os_name: str
) -> PathSnapshot:
    from pathkeeper.core.diagnostics import join_path

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
    from pathkeeper.core.diagnostics import analyze_snapshot, join_path

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


def _preflight_write(
    current: PathSnapshot, updated: PathSnapshot, scope: Scope, adapter: object
) -> None:
    if scope not in {Scope.SYSTEM, Scope.ALL}:
        return
    if (
        current.system_path == updated.system_path
        and current.system_env_vars == updated.system_env_vars
    ):
        return
    checker = getattr(adapter, "ensure_system_writable", None)
    if callable(checker):
        checker()


def _restore(args: argparse.Namespace) -> int:
    from pathkeeper.core.diff import compute_diff, render_diff
    from pathkeeper.core.path_writer import write_changed_snapshot

    logger.info(
        "Restoring PATH from backup %s with scope=%s", args.identifier, args.scope
    )
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
    from pathkeeper.core.dedupe import dedupe_entries
    from pathkeeper.core.diagnostics import join_path
    from pathkeeper.core.diff import compute_diff, render_diff
    from pathkeeper.core.path_writer import write_changed_snapshot
    from pathkeeper.models import PathSnapshot

    logger.info(
        "Deduping PATH with scope=%s keep=%s remove_invalid=%s",
        args.scope,
        args.keep,
        args.remove_invalid,
    )
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    os_name = normalized_os_name()
    from pathkeeper.core.diagnostics import canonicalize_entry

    if scope is Scope.ALL:
        system_result = dedupe_entries(
            snapshot.system_path,
            os_name,
            keep=args.keep,
            remove_invalid=args.remove_invalid,
        )
        # Pre-seed user dedup with canonicals from the cleaned system entries so
        # cross-scope duplicates (same path in both system and user) are removed
        # from the user section (system entries take precedence).
        system_seen = {canonicalize_entry(e, os_name) for e in system_result.cleaned}
        user_result = dedupe_entries(
            snapshot.user_path,
            os_name,
            keep=args.keep,
            remove_invalid=args.remove_invalid,
            pre_seen=system_seen,
        )
        system_diff = render_diff(
            compute_diff(system_result.original, system_result.cleaned, os_name)
        )
        user_diff = render_diff(
            compute_diff(user_result.original, user_result.cleaned, os_name)
        )
        print(t.bold("System diff:"))
        print(system_diff)
        print(t.bold("\nUser diff:"))
        print(user_diff)
        has_changes = (
            system_result.original != system_result.cleaned
            or user_result.original != user_result.cleaned
        )
        if not has_changes:
            print(t.ok("No duplicates found. Nothing to do."))
            return 0
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
        print(t.ok("Dedupe complete."))
        return 0
    original = snapshot.entries_for_scope(scope)
    result = dedupe_entries(
        original, os_name, keep=args.keep, remove_invalid=args.remove_invalid
    )
    print(render_diff(compute_diff(result.original, result.cleaned, os_name)))
    if result.original == result.cleaned:
        print(t.ok("No duplicates found. Nothing to do."))
        return 0
    if args.dry_run:
        return 0
    updated = _snapshot_with_scope(snapshot, scope, result.cleaned, os_name)
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-dedupe", note="Before dedupe", quiet=False)
    _confirm("Apply dedupe changes?", force=args.force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Dedupe complete for scope=%s", args.scope)
    print(t.ok("Dedupe complete."))
    return 0


def _populate_select_interactive(
    grouped: dict[str, list[PopulateMatch]],
) -> list[PopulateMatch]:
    """Prompt category-by-category; return chosen PopulateMatch list."""
    selected = []
    categories = list(grouped.keys())
    total = sum(len(v) for v in grouped.values())
    print(
        t.dim(f"Found {total} path(s) across {len(categories)} category/categories.")
        + "\n"
    )
    hint = t.dim("  [a]ll in category  [s]kip  [q]uit  or numbers e.g. '1 3'")
    for cat in categories:
        items = grouped[cat]
        print(t.category(f"  {cat}"))
        for i, item in enumerate(items, 1):
            exe_hint = ""
            if item.found_executables:
                names = ", ".join(item.found_executables[:8])
                suffix = ", …" if len(item.found_executables) > 8 else ""
                exe_hint = t.dim(f"  [{names}{suffix}]")
            print(
                f"    {t.dim(str(i) + '.')} {t.accent(item.path)}  {t.dim('(' + item.name + ')')}{exe_hint}"
            )
        print(hint)
        while True:
            answer = input(t.prompt("  > ")).strip().lower()
            if answer in {"a", "all", "y", "yes"}:
                selected.extend(items)
                print(
                    t.ok(f"  + All {len(items)} item(s) from '{cat}' selected.") + "\n"
                )
                break
            if answer in {"s", "skip", "", "n", "no"}:
                print(t.dim(f"  Skipped '{cat}'.") + "\n")
                break
            if answer in {"q", "quit"}:
                raise UserCancelledError("Populate cancelled.")
            # numeric selection
            try:
                indices = [int(tok) - 1 for tok in answer.split()]
                if all(0 <= idx < len(items) for idx in indices):
                    chosen = [items[idx] for idx in indices]
                    selected.extend(chosen)
                    print(
                        t.ok(f"  + {len(chosen)} item(s) from '{cat}' selected.") + "\n"
                    )
                    break
            except ValueError:
                pass
            print(
                t.warn(
                    f"  Invalid input. Enter 'a', 's', numbers (1-{len(items)}), or 'q'."
                )
            )
    return selected


def _populate(args: argparse.Namespace) -> int:
    from pathkeeper.core.path_writer import write_changed_snapshot
    from pathkeeper.core.populate import discover_tools, group_matches, load_catalog

    logger.info(
        "Populating PATH for scope=%s category=%s", args.scope, args.category or "all"
    )
    config = load_config()
    adapter = get_platform_adapter(config)
    if args.list_catalog:
        print((backups_home().parent / "known_tools.toml").read_text(encoding="utf-8"))
        return 0
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    catalog = load_catalog(config)
    existing = snapshot.entries_for_scope(Scope.ALL)
    matches = discover_tools(
        catalog, existing, os_name=normalized_os_name(), category=args.category
    )
    if not matches:
        logger.info("No populate matches found.")
        print(t.ok("No missing tool directories found."))
        return 0
    logger.info("Found %s populate match(es).", len(matches))
    grouped = group_matches(matches)
    for cat, items in grouped.items():
        print(t.category(cat))
        for item in items:
            exe_hint = ""
            if item.found_executables:
                names = ", ".join(item.found_executables[:8])
                suffix = ", …" if len(item.found_executables) > 8 else ""
                exe_hint = t.dim(f"  [{names}{suffix}]")
            print(
                f"  {t.dim('-')} {t.accent(item.path)} {t.dim('(' + item.name + ')')}{exe_hint}"
            )
    if args.dry_run:
        print(t.dry_run("[dry-run] No changes written."))
        return 0
    if args.all or args.force:
        selected = matches
    else:
        print()
        selected = _populate_select_interactive(grouped)
    if not selected:
        print(t.dim("Nothing selected. PATH unchanged."))
        return 0
    selected_paths = [item.path for item in selected]
    updated = _snapshot_with_scope(
        snapshot,
        scope,
        [*snapshot.entries_for_scope(scope), *selected_paths],
        normalized_os_name(),
    )
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-populate", note="Before populate", quiet=False)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info(
        "Populate complete for scope=%s: added %d path(s).",
        args.scope,
        len(selected_paths),
    )
    print(t.ok(f"Populate complete. Added {len(selected_paths)} path(s)."))
    return 0


def _scope_has_dedupe_changes(
    entries: list[str], *, os_name: str, keep: str, remove_invalid: bool
) -> bool:
    from pathkeeper.core.dedupe import dedupe_entries

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
    repairs: list[tuple[str, TruncatedPathRepair]],
    *,
    force: bool,
) -> list[tuple[str, TruncatedPathRepair]]:
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
        choice = _prompt_choice(
            "Choose a repair number (Enter to skip): ",
            upper_bound=len(repair.candidates),
        )
        if choice is None:
            print("Skipped this repair.")
            print()
            continue
        selected.append((repair.candidates[choice].path, repair))
        print()
    return selected


def _repair_truncated(args: argparse.Namespace) -> int:
    from pathkeeper.core.diagnostics import join_path
    from pathkeeper.core.diff import compute_diff, render_diff
    from pathkeeper.core.path_writer import write_changed_snapshot
    from pathkeeper.core.repair_truncated import find_truncated_repairs
    from pathkeeper.models import PathSnapshot

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
            print(
                f"[{repair.scope.value}] Entry #{repair.display_index}: {repair.value}"
            )
            for index, candidate in enumerate(repair.candidates, start=1):
                print(f"  {index}. {candidate.path} ({candidate.source})")
        return 0
    selections = _select_truncated_repairs(
        [(repair.value, repair) for repair in repairs], force=args.force
    )
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
        print(
            render_diff(
                compute_diff(snapshot.system_path, updated.system_path, os_name)
            )
        )
    if updated.user_path != snapshot.user_path:
        if updated.system_path != snapshot.system_path:
            print()
        print("User diff:")
        print(render_diff(compute_diff(snapshot.user_path, updated.user_path, os_name)))
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(
        tag="pre-repair-truncated",
        note="Before repairing truncated PATH entries",
        quiet=False,
    )
    _confirm("Apply truncated PATH repairs?", force=args.force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info("Truncated PATH repair complete for scope=%s", args.scope)
    print("Truncated PATH repair complete.")
    return 0


def _split_long(args: argparse.Namespace) -> int:
    from pathkeeper.core.path_writer import write_changed_snapshot
    from pathkeeper.core.split_long import (
        apply_plan_to_snapshot,
        build_split_long_plan,
        render_plan,
    )

    logger.info(
        "Splitting long PATH for scope=%s max_length=%s chunk_length=%s",
        args.scope,
        args.max_length,
        args.chunk_length,
    )
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    scope = _scope(args.scope)
    os_name = normalized_os_name()
    env_reader_name = (
        "read_system_environment" if scope is Scope.SYSTEM else "read_user_environment"
    )
    read_environment = getattr(adapter, env_reader_name, None)
    if not callable(read_environment):
        raise PathkeeperError(
            "split-long requires Windows environment-variable support."
        )
    plan = build_split_long_plan(
        snapshot,
        scope=scope,
        os_name=os_name,
        environment=read_environment(),
        max_length=args.max_length,
        chunk_length=args.chunk_length,
        var_prefix=args.var_prefix,
    )
    print(render_plan(plan))
    if not plan.changed:
        return 0
    if args.dry_run:
        print(t.dry_run("[dry-run] No changes written."))
        return 0
    updated = apply_plan_to_snapshot(snapshot, plan)
    _preflight_write(snapshot, updated, scope, adapter)
    _backup_now(tag="pre-split-long", note="Before split-long", quiet=False)
    _confirm("Apply split-long changes?", force=args.force)
    write_changed_snapshot(adapter, snapshot, updated, scope)
    logger.info(
        "Split-long complete for scope=%s with %d helper variable(s).",
        args.scope,
        len(plan.helper_vars),
    )
    print(
        t.ok(
            f"Split-long complete. PATH now uses {len(plan.helper_vars)} helper variable(s)."
        )
    )
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
        print(
            "System PATH changes need an elevated shell, but user PATH changes can still be applied."
        )
        if not _prompt_yes_no(
            "Restrict dedupe to the user PATH instead?", default=True
        ):
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
    dry_run: bool,
    os_name: str,
    scope: Scope,
    session: EditSession,
    snapshot: PathSnapshot,
) -> int:
    from pathkeeper.core.diff import render_diff
    from pathkeeper.core.path_writer import write_changed_snapshot

    diff = session.diff()
    print(render_diff(diff))
    if diff.added == [] and diff.removed == [] and diff.reordered == []:
        print("No staged changes to write.")
        return 0
    if dry_run:
        print("Dry run: edit changes were not written.")
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
    import shlex

    from pathkeeper.core.diff import render_diff
    from pathkeeper.core.edit import EditSession

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
                session.move(
                    _entry_number(parts[1], session.entries), _position_number(parts[2])
                )
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
                session.swap(
                    _entry_number(parts[1], session.entries),
                    _entry_number(parts[2], session.entries),
                )
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
                    dry_run=False,
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
    from pathkeeper.core.edit import EditSession

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
        session.replace(
            _entry_index(session.entries, args.replace_value), args.new_path
        )
    return _write_edit_session(
        adapter=adapter,
        args_force=args.force,
        dry_run=args.dry_run,
        os_name=os_name,
        scope=scope,
        session=session,
        snapshot=snapshot,
    )


def _schedule(args: argparse.Namespace) -> int:
    from pathkeeper.core.schedule import (
        install_schedule,
        remove_schedule,
        schedule_status,
    )

    os_name = normalized_os_name()
    if args.schedule_command == "status":
        status = schedule_status(os_name)
        if status.enabled:
            logger.info("Schedule is enabled: %s", status.detail)
            print(f"Schedule is enabled: {status.detail}")
        else:
            logger.warning("Schedule is disabled.")
            print(
                "Schedule is disabled. Run `pathkeeper schedule install` to enable automatic backups."
            )
        return 0
    if args.schedule_command == "install":
        trigger = getattr(args, "trigger", "startup")
        if getattr(args, "dry_run", False):
            print(
                "Dry run: would install scheduled backups "
                f"for os={os_name} interval={args.interval} trigger={trigger}."
            )
            return 0
        logger.info(
            "Installing schedule with interval=%s trigger=%s", args.interval, trigger
        )
        print(install_schedule(os_name, args.interval, trigger=trigger))
        return 0
    if getattr(args, "dry_run", False):
        print(f"Dry run: would remove scheduled backups for os={os_name}.")
        return 0
    logger.info("Removing schedule.")
    print(remove_schedule(os_name))
    return 0


def _interactive_schedule_status(_args: argparse.Namespace) -> int:
    from pathkeeper.core.schedule import schedule_status

    os_name = normalized_os_name()
    status = schedule_status(os_name)
    if status.enabled:
        print(f"Schedule is enabled: {status.detail}")
        return 0
    print("Scheduled backups are not set up yet.")
    if not _prompt_yes_no("Install automatic backups now?", default=True):
        print("Scheduled backups were not changed.")
        return 0
    install_args = argparse.Namespace(
        schedule_command="install",
        interval="startup",
        trigger="startup",
        command="schedule",
    )
    try:
        return _schedule(install_args)
    except PermissionDeniedError:
        if os_name != "windows":
            raise
        print("Installing a startup task on Windows needs an elevated shell.")
        if not _prompt_yes_no(
            "Install a per-user logon backup task instead?", default=True
        ):
            print("Scheduled backups were not changed.")
            return 0
        fallback_args = argparse.Namespace(
            schedule_command="install",
            interval="startup",
            trigger="logon",
            command="schedule",
        )
        try:
            return _schedule(fallback_args)
        except PermissionDeniedError:
            print("Windows denied creation of the per-user logon task too.")
            print(
                "Run pathkeeper from an elevated shell to install the startup task, or ask your administrator if Task Scheduler is blocked."
            )
            return 0


def _diff(args: argparse.Namespace) -> int:
    from pathkeeper.core.diff import compute_diff, render_diff

    os_name = normalized_os_name()
    scope = _scope(args.scope)
    records = list_backups(backups_home())
    if not records:
        raise PathkeeperError("No backups available.")

    def _resolve(identifier: str) -> BackupRecord:
        if identifier.isdigit():
            idx = int(identifier) - 1
            if idx < 0 or idx >= len(records[:20]):
                raise PathkeeperError(f"Backup number out of range: {identifier}")
            return records[idx]
        return resolve_backup(identifier, backups_home())

    record_a = _resolve(args.backup_a)
    record_b = _resolve(args.backup_b)
    name_a = record_a.source_file.name if record_a.source_file else args.backup_a
    name_b = record_b.source_file.name if record_b.source_file else args.backup_b
    print(t.dim(f"Comparing {name_a}  ->  {name_b}"))
    print()
    if scope in {Scope.SYSTEM, Scope.ALL}:
        diff = compute_diff(record_a.system_path, record_b.system_path, os_name)
        print(t.bold("System PATH:"))
        print(render_diff(diff))
        print()
    if scope in {Scope.USER, Scope.ALL}:
        diff = compute_diff(record_a.user_path, record_b.user_path, os_name)
        print(t.bold("User PATH:"))
        print(render_diff(diff))
    return 0


def _shadow(args: argparse.Namespace) -> int:
    from pathkeeper.core.shadow import find_shadows

    scope = _scope(args.scope)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    groups = find_shadows(
        system_entries=snapshot.system_path,
        user_entries=snapshot.user_path,
        os_name=os_name,
        scope=scope,
    )
    if not groups:
        print(t.ok("No shadowed executables found."))
        return 0
    if getattr(args, "as_json", False):
        import json

        payload = [
            {
                "name": g.name,
                "entries": [
                    {"directory": e.directory, "scope": e.scope.value, "index": e.index}
                    for e in g.entries
                ],
            }
            for g in groups
        ]
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Found {t.warn(str(len(groups)))} shadowed executable(s):\n")
    for group in groups:
        print(f"  {t.bold(group.name)}")
        for i, entry in enumerate(group.entries):
            prefix = t.ok("winner") if i == 0 else t.warn("shadow")
            scope_label = t.dim(f"({entry.scope.value})")
            print(f"    {prefix}  #{entry.index} {scope_label} {entry.directory}")
        print()
    return 0


def _diff_current(args: argparse.Namespace) -> int:
    from pathkeeper.core.diff import compute_diff, render_diff

    scope = _scope(args.scope)
    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    identifier = getattr(args, "identifier", None)
    if identifier is None:
        records = _recent_backups(limit=20)
        if not records:
            print("No backups available.")
            return 0
        print("Most recent backups:")
        _render_backup_listing(records, numbered=True)
        identifier = input("Select backup number (blank for 1): ").strip() or "1"
    record, _records = _select_backup(identifier)
    name = record.source_file.name if record.source_file else identifier
    print(t.dim(f"Comparing backup {name}  ->  current PATH"))
    print()
    if scope in {Scope.SYSTEM, Scope.ALL}:
        diff = compute_diff(record.system_path, snapshot.system_path, os_name)
        print(t.bold("System PATH:"))
        print(render_diff(diff))
        print()
    if scope in {Scope.USER, Scope.ALL}:
        diff = compute_diff(record.user_path, snapshot.user_path, os_name)
        print(t.bold("User PATH:"))
        print(render_diff(diff))
    return 0


def _runtime_entries(_args: argparse.Namespace) -> int:
    from pathkeeper.core.runtime_diff import detect_runtime_entries

    config = load_config()
    adapter = get_platform_adapter(config)
    snapshot = read_snapshot(adapter)
    os_name = normalized_os_name()
    entries = detect_runtime_entries(snapshot, os_name)
    runtime_only = [e for e in entries if not e.persisted]
    if not runtime_only:
        print(
            t.ok(
                "All PATH entries match the persisted PATH. "
                "No runtime-only additions detected."
            )
        )
        return 0
    print(
        f"Found {t.warn(str(len(runtime_only)))} runtime-only PATH "
        f"entry/entries (not in registry / rc files):\n"
    )
    for entry in entries:
        if entry.persisted:
            scope_label = f"({entry.scope.value})" if entry.scope else ""
            print(f"  {t.ok('[persisted]')} {t.dim(scope_label)} {entry.value}")
        else:
            print(f"  {t.warn('[runtime]')}  {t.accent(entry.value)}")
    return 0


_SHELL_STARTUP_MARKER = "# pathkeeper backup (added by pathkeeper shell-startup)"
_SHELL_STARTUP_LINE = "pathkeeper backup --quiet --tag auto"


def _shell_startup_command() -> str:
    """Return the shell command to invoke pathkeeper.

    Prefers the installed ``pathkeeper`` script on PATH; falls back to
    ``python -m pathkeeper`` using the running interpreter so the line works
    regardless of how the package was installed.
    """
    import shutil
    import sys

    if shutil.which("pathkeeper"):
        return "pathkeeper"
    # Absolute path to the interpreter so the line works in non-activated shells.
    return f'"{sys.executable}" -m pathkeeper'


def _detect_shell_rc() -> tuple[str, str] | None:
    """Return (shell_name, rc_file_path) for the running shell, or None."""
    import os as _os

    # Git Bash / MSYS2 / Cygwin all set SHELL to something like /usr/bin/bash
    shell_env = _os.environ.get("SHELL", "")
    if "fish" in shell_env:
        rc = _os.path.expanduser("~/.config/fish/config.fish")
        return ("fish", rc)
    if "bash" in shell_env:
        rc = _os.path.expanduser("~/.bashrc")
        return ("bash", rc)
    if "zsh" in shell_env:
        rc = _os.path.expanduser("~/.zshrc")
        return ("zsh", rc)
    # Windows: fall back to PowerShell profile
    profile_env = _os.environ.get("USERPROFILE", _os.path.expanduser("~"))
    pwsh_profile = _os.path.join(
        profile_env,
        "Documents",
        "WindowsPowerShell",
        "Microsoft.PowerShell_profile.ps1",
    )
    return ("powershell", pwsh_profile)


def _shell_startup_rc_for(shell: str | None) -> tuple[str, str]:
    import os as _os

    if shell == "fish":
        return ("fish", _os.path.expanduser("~/.config/fish/config.fish"))
    if shell in {"bash", None}:
        return ("bash", _os.path.expanduser("~/.bashrc"))
    if shell == "zsh":
        return ("zsh", _os.path.expanduser("~/.zshrc"))
    if shell in {"powershell", "pwsh"}:
        profile = _os.path.join(
            _os.environ.get("USERPROFILE", _os.path.expanduser("~")),
            "Documents",
            "WindowsPowerShell",
            "Microsoft.PowerShell_profile.ps1",
        )
        return ("powershell", profile)
    raise PathkeeperError(f"Unknown shell: {shell!r}")


def _shell_startup_backup_line(shell_name: str) -> str:
    cmd = _shell_startup_command()
    line = f"{cmd} backup --quiet --tag auto"
    if shell_name == "fish":
        return f"{line}  # {_SHELL_STARTUP_MARKER}"
    if shell_name in {"bash", "zsh"}:
        return f"{line}  {_SHELL_STARTUP_MARKER}"
    # PowerShell
    return f"{line}  <# {_SHELL_STARTUP_MARKER} #>"


def _shell_startup_already_present(text: str) -> bool:
    return _SHELL_STARTUP_MARKER in text


def _shell_startup(args: argparse.Namespace) -> int:
    import os as _os
    from pathlib import Path as _Path

    if args.rc_file:
        shell_name = args.shell or "bash"
        rc_file = _os.path.expanduser(args.rc_file)
    else:
        shell_name, rc_file = _shell_startup_rc_for(args.shell)

    rc_path = _Path(rc_file)
    existing_text = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
    injection_line = _shell_startup_backup_line(shell_name)

    if args.remove:
        if not _shell_startup_already_present(existing_text):
            print(t.dim(f"Marker not found in {rc_file}. Nothing to remove."))
            return 0
        lines = existing_text.splitlines(keepends=True)
        new_lines = [ln for ln in lines if _SHELL_STARTUP_MARKER not in ln]
        new_text = "".join(new_lines)
        if args.dry_run:
            print(
                t.dry_run(
                    f"[dry-run] Would remove pathkeeper startup line from {rc_file}"
                )
            )
            return 0
        rc_path.write_text(new_text, encoding="utf-8")
        print(t.ok(f"Removed pathkeeper startup line from {rc_file}."))
        return 0

    if _shell_startup_already_present(existing_text):
        print(t.dim(f"Pathkeeper startup line is already present in {rc_file}."))
        return 0

    new_text = existing_text.rstrip("\n") + f"\n{injection_line}\n"
    if args.dry_run:
        print(t.dry_run(f"[dry-run] Would append to {rc_file}:"))
        print(t.dry_run(f"  {injection_line}"))
        return 0
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_path.write_text(new_text, encoding="utf-8")
    print(t.ok(f"Added startup backup to {rc_file}."))
    print(
        t.dim(
            "Pathkeeper will run 'backup --quiet' each time you open a new shell session."
        )
    )
    if shell_name == "fish":
        print(
            t.dim(
                "Re-open your terminal or run 'source ~/.config/fish/config.fish' to activate."
            )
        )
    elif shell_name == "zsh":
        print(t.dim("Re-open your terminal or run 'source ~/.zshrc' to activate."))
    else:
        print(
            t.dim("Re-open your terminal or run 'source ~/.bashrc' (bash) to activate.")
        )
    return 0


def _selfcheck(_args: argparse.Namespace) -> int:
    from pathkeeper.core.selfcheck import _STATUS_FAIL, _STATUS_WARN, run_selfcheck

    report = run_selfcheck()
    print(t.header("  pathkeeper selfcheck"))
    print()
    for check in report.checks:
        if check.status == _STATUS_FAIL:
            marker = t.error("FAIL")
        elif check.status == _STATUS_WARN:
            marker = t.warn("WARN")
        else:
            marker = t.ok("PASS")
        padded = check.name.ljust(24, ".")
        print(f"  {marker}  {padded} {check.detail}")
        if check.remediation and check.status != "pass":
            print(f"            {t.accent('->')} {check.remediation}")
    print()
    if report.passed:
        print(t.ok("  Overall: all checks passed"))
    else:
        fail_count = sum(1 for c in report.checks if c.status == _STATUS_FAIL)
        warn_count = sum(1 for c in report.checks if c.status == _STATUS_WARN)
        parts = []
        if fail_count:
            parts.append(t.error(f"{fail_count} failed"))
        if warn_count:
            parts.append(t.warn(f"{warn_count} warnings"))
        print(t.warn(f"  Overall: {', '.join(parts)}"))
    return report.exit_code


def _first_run_wizard() -> int:
    """Interactive onboarding for new users (no ~/.pathkeeper/ found)."""
    from pathkeeper.config import ensure_app_state

    print(t.header("Welcome to pathkeeper!"))
    print()
    print("pathkeeper backs up and restores your PATH environment variable.")
    print("It looks like this is your first time running pathkeeper.")
    print()

    # Step 1: Initialize app state
    print(t.accent("Setting up pathkeeper..."))
    ensure_app_state()
    print(t.ok("  Created ~/.pathkeeper/ with default config and tool catalog."))
    print()

    # Step 2: PATH health check
    print(t.accent("Checking your current PATH..."))
    _snapshot, report = _read_current_report(Scope.ALL)
    s = report.summary
    health = (
        t.ok("healthy")
        if s.invalid == 0 and s.duplicates == 0 and s.empty == 0
        else t.warn("needs attention")
    )
    print(
        f"  {s.total} entries  {t.ok(f'valid: {s.valid}')}  "
        f"{(t.error if s.invalid else t.dim)(f'invalid: {s.invalid}')}  "
        f"{(t.warn if s.duplicates else t.dim)(f'dup: {s.duplicates}')}  "
        f"— {health}"
    )
    for warning in s.warnings:
        print(t.warn(f"  ! {warning}"))
    print()

    # Step 3: Create first backup
    if _prompt_yes_no("Create your first backup now?", default=True):
        _backup_now(
            tag="manual",
            note="first backup (created by onboarding wizard)",
            quiet=False,
        )
        print()

        # Step 4: Shell startup hook
        detected = _detect_shell_rc()
        if detected:
            shell_name, rc_file = detected
            if _prompt_yes_no(f"Install startup hook into {rc_file}?", default=True):
                _shell_startup(
                    argparse.Namespace(
                        shell=shell_name,
                        rc_file=None,
                        dry_run=False,
                        remove=False,
                    )
                )
                print()

    # Step 5: Done
    print(t.ok("Setup complete!"))
    print(t.dim("Run 'pathkeeper' again to open the main menu."))
    return 0


def _interactive() -> int:
    from pathkeeper.interactive import MenuEntry, run_interactive

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

        def _no_backups_restore_handler(_args: argparse.Namespace) -> int:
            print("No backups available yet.")
            return 0

        restore_handler = _no_backups_restore_handler

    dispatch = {
        "1": MenuEntry(
            "Inspect",
            "Review PATH entries and their health",
            parser.parse_args(["inspect"]),
            _print_inspect,
        ),
        "2": MenuEntry(
            "Doctor",
            "Diagnose problems and suggest repairs",
            parser.parse_args(["doctor"]),
            _print_doctor,
        ),
        "3": MenuEntry(
            "Create backup",
            "Save the current PATH snapshot",
            parser.parse_args(["backup"]),
            _backup_command,
        ),
        "4": MenuEntry(
            "List backups",
            "Browse recent backups and hashes",
            parser.parse_args(["backups", "list"]),
            list_backups_handler,
        ),
        "5": MenuEntry(
            "Show backup",
            "Inspect one backup in detail",
            parser.parse_args(["backups", "show"]),
            show_backup_handler,
        ),
        "6": MenuEntry(
            "Restore",
            "Restore the most recent backup",
            restore_namespace,
            restore_handler,
        ),
        "7": MenuEntry(
            "Dedupe",
            "Remove duplicates and broken entries",
            parser.parse_args(["dedupe"]),
            _interactive_dedupe,
        ),
        "8": MenuEntry(
            "Populate",
            "Discover common tool directories",
            parser.parse_args(["populate"]),
            _populate,
        ),
        "9": MenuEntry(
            "Edit",
            "Stage PATH changes in an editor",
            parser.parse_args(["edit"]),
            _edit,
        ),
        "10": MenuEntry(
            "Repair truncated",
            "Repair entries missing leading path segments",
            parser.parse_args(["repair-truncated"]),
            _repair_truncated,
        ),
        "11": MenuEntry(
            "Split long",
            "Shorten Windows PATH with helper variables",
            parser.parse_args(["split-long"]),
            _split_long,
        ),
        "12": MenuEntry(
            "Schedule status",
            "Check or install automatic backups",
            parser.parse_args(["schedule", "status"]),
            _interactive_schedule_status,
        ),
        "13": MenuEntry(
            "Shell startup",
            "Inject backup hook into shell startup file",
            parser.parse_args(["shell-startup"]),
            _shell_startup,
        ),
        "14": MenuEntry(
            "Shadows",
            "Find executables shadowed by earlier PATH entries",
            parser.parse_args(["shadow"]),
            _shadow,
        ),
        "15": MenuEntry(
            "Diff vs current",
            "Compare a backup against the current live PATH",
            parser.parse_args(["diff-current"]),
            _diff_current,
        ),
        "16": MenuEntry(
            "Runtime entries",
            "Show PATH entries injected at runtime",
            parser.parse_args(["runtime-entries"]),
            _runtime_entries,
        ),
        "17": MenuEntry(
            "Self-check",
            "Verify pathkeeper installation health",
            parser.parse_args(["selfcheck"]),
            _selfcheck,
        ),
    }
    _print_interactive_startup_banner()
    return run_interactive(dispatch)


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        import argcomplete

        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.log_level)
    _init_theme(args)
    if args.command == "gui" or getattr(args, "gui", False):
        from pathkeeper.gui.app import launch_gui

        # Default GUI logging to INFO so background errors are visible.
        if args.log_level == "warning":
            _configure_logging("info")
        return launch_gui()
    if args.command is None:
        from pathkeeper.config import app_home

        if not app_home().exists():
            return _first_run_wizard()
        return _interactive()
    if args.command == "inspect":
        return _print_inspect(args)
    if args.command == "doctor":
        return _print_doctor(args)
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
    if args.command == "split-long":
        return _split_long(args)
    if args.command == "edit":
        return _edit(args)
    if args.command == "schedule":
        return _schedule(args)
    if args.command == "diff":
        return _diff(args)
    if args.command == "shadow":
        return _shadow(args)
    if args.command == "diff-current":
        return _diff_current(args)
    if args.command == "runtime-entries":
        return _runtime_entries(args)
    if args.command == "shell-startup":
        return _shell_startup(args)
    if args.command == "selfcheck":
        return _selfcheck(args)
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
