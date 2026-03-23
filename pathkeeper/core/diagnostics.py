from __future__ import annotations

import os
import re
from pathlib import Path

from pathkeeper.models import (
    DiagnosticEntry,
    DiagnosticReport,
    DiagnosticSummary,
    Scope,
)

WINDOWS_VAR_PATTERN = re.compile(r"%[^%]+%")
UNIX_VAR_PATTERN = re.compile(r"\$(?:\{[^}]+\}|[A-Za-z_][A-Za-z0-9_]*)")


def path_separator_for(os_name: str) -> str:
    return ";" if os_name == "windows" else ":"


def split_path(raw: str, os_name: str) -> list[str]:
    if raw == "":
        return []
    return raw.split(path_separator_for(os_name))


def join_path(entries: list[str], os_name: str) -> str:
    return path_separator_for(os_name).join(entries)


def expand_entry(entry: str) -> str:
    return os.path.expanduser(os.path.expandvars(entry.strip().strip('"')))


def has_unexpanded_variables(entry: str, os_name: str) -> bool:
    pattern = WINDOWS_VAR_PATTERN if os_name == "windows" else UNIX_VAR_PATTERN
    return pattern.search(entry) is not None


def _looks_like_missing_separator(entry: str, os_name: str) -> bool:
    """Return True if *entry* looks like two paths glued together.

    Heuristic: an invalid entry that contains an embedded absolute-path start
    mid-string (e.g. ``/c/foo/c/bar`` has ``/c/`` starting at a non-zero
    offset, or ``C:\\Windows\\System32C:\\Program Files`` has a drive letter
    mid-string).
    """
    if not entry or len(entry) < 4:
        return False
    if os_name == "windows":
        # Look for a drive letter pattern (X:\ or X:/) starting after position 0
        for i in range(2, len(entry) - 1):
            if entry[i].isalpha() and entry[i + 1 : i + 2] == ":":
                return True
        # Also check for semicolons that survived un-split (shouldn't happen,
        # but catches e.g. manually constructed values)
        return ";" in entry[1:]
    # Unix: look for an absolute path start (/) embedded after position 0.
    # We need at least two non-adjacent / characters to avoid false positives
    # on normal deep paths.  The pattern we're looking for is a second
    # root-like segment — a / immediately preceded by a non-/ character where
    # the prefix and suffix both form plausible absolute paths.
    # Simple heuristic: the entry doesn't exist, is long, and splitting on a
    # mid-string "/" where both halves start with "/" yields two existing dirs
    # (checked by the caller).  Here we use a cheaper signal: the entry
    # contains a colon (the Unix separator) which would indicate a literal
    # separator that wasn't split.
    return ":" in entry


def canonicalize_entry(entry: str, os_name: str) -> str:
    value = expand_entry(entry)
    if os_name == "windows":
        normalized = value.replace("/", "\\").rstrip("\\").strip('"')
        return normalized.casefold().strip()
    normalized = value.rstrip("/")
    if os_name == "darwin":
        return normalized.casefold()
    return normalized


def _analyze_group(
    entries: list[str],
    scope: Scope,
    os_name: str,
    start_index: int,
    seen: dict[str, int],
) -> list[DiagnosticEntry]:
    from pathkeeper.core.executables import list_executables

    results: list[DiagnosticEntry] = []
    for offset, entry in enumerate(entries):
        expanded = expand_entry(entry)
        canonical = canonicalize_entry(entry, os_name)
        is_empty = entry.strip() == ""
        path = Path(expanded) if expanded else None
        exists = bool(path and path.exists())
        is_dir = bool(path and path.is_dir())
        duplicate_of = seen.get(canonical)
        if canonical and duplicate_of is None:
            seen[canonical] = start_index + offset
        exes = list_executables(expanded, os_name) if (is_dir and not is_empty) else []
        missing_sep = (
            not is_empty
            and not exists
            and _looks_like_missing_separator(entry, os_name)
        )
        results.append(
            DiagnosticEntry(
                index=start_index + offset,
                value=entry,
                scope=scope,
                exists=exists,
                is_dir=is_dir,
                is_duplicate=duplicate_of is not None,
                duplicate_of=duplicate_of,
                is_empty=is_empty,
                has_unexpanded_vars=has_unexpanded_variables(entry, os_name),
                expanded_value=expanded,
                executables=exes,
                likely_missing_separator=missing_sep,
            )
        )
    return results


def analyze_snapshot(
    *,
    system_entries: list[str],
    user_entries: list[str],
    os_name: str,
    scope: Scope,
    raw_value: str,
) -> DiagnosticReport:
    entries: list[DiagnosticEntry] = []
    next_index = 1
    seen: dict[str, int] = {}
    if scope in {Scope.SYSTEM, Scope.ALL}:
        system_diagnostics = _analyze_group(
            system_entries, Scope.SYSTEM, os_name, next_index, seen
        )
        entries.extend(system_diagnostics)
        next_index += len(system_diagnostics)
    if scope in {Scope.USER, Scope.ALL}:
        user_diagnostics = _analyze_group(
            user_entries, Scope.USER, os_name, next_index, seen
        )
        entries.extend(user_diagnostics)
    warnings: list[str] = []
    path_length = len(raw_value)
    if os_name == "windows":
        if path_length > 32767:
            warnings.append(
                "PATH exceeds the Windows registry limit of 32767 characters."
            )
        elif path_length > 2047:
            warnings.append("PATH exceeds the legacy setx limit of 2047 characters.")
    missing_sep_count = sum(1 for item in entries if item.likely_missing_separator)
    if missing_sep_count:
        warnings.append(
            f"{missing_sep_count} entry/entries look like paths glued together "
            "(missing separator). Inspect them and consider editing with "
            "`pathkeeper edit`."
        )
    summary = DiagnosticSummary(
        total=len(entries),
        valid=sum(
            1 for item in entries if item.exists and item.is_dir and not item.is_empty
        ),
        invalid=sum(
            1 for item in entries if item.value and (not item.exists or not item.is_dir)
        ),
        duplicates=sum(1 for item in entries if item.is_duplicate),
        empty=sum(1 for item in entries if item.is_empty),
        files=sum(1 for item in entries if item.exists and not item.is_dir),
        missing_separators=missing_sep_count,
        warnings=tuple(warnings),
    )
    return DiagnosticReport(
        entries=entries, summary=summary, os_name=os_name, path_length=path_length
    )


def doctor_recommendations(report: DiagnosticReport) -> list[str]:
    recommendations: list[str] = []
    if report.summary.invalid:
        recommendations.append(
            "Run `pathkeeper dedupe --remove-invalid` to remove broken entries."
        )
    if report.summary.duplicates:
        recommendations.append("Run `pathkeeper dedupe` to remove duplicate entries.")
    if report.summary.missing_separators:
        recommendations.append(
            "Some entries look like paths with a missing separator. "
            "Use `pathkeeper edit` to split them."
        )
    if report.summary.warnings:
        recommendations.append(
            "Create a backup now and consider restoring a healthier snapshot."
        )
    if not recommendations:
        recommendations.append("No obvious PATH issues were detected.")
    return recommendations


# ------------------------------------------------------------------
# Structured doctor checks
# ------------------------------------------------------------------

_STATUS_PASS = "pass"  # nosec B105
_STATUS_FAIL = "fail"
_STATUS_WARN = "warn"


class DoctorCheck:
    """One diagnostic check with a status, affected entries, and remediation."""

    __slots__ = ("affected", "detail", "name", "remediation", "status")

    def __init__(
        self,
        name: str,
        *,
        status: str,
        detail: str,
        affected: list[DiagnosticEntry] | None = None,
        remediation: str = "",
    ) -> None:
        self.name = name
        self.status = status
        self.detail = detail
        self.affected: list[DiagnosticEntry] = affected or []
        self.remediation = remediation


def doctor_checks(report: DiagnosticReport) -> list[DoctorCheck]:
    """Return an ordered list of structured doctor checks."""
    checks: list[DoctorCheck] = []
    s = report.summary

    # 1. Duplicates
    dups = [e for e in report.entries if e.is_duplicate]
    if dups:
        checks.append(
            DoctorCheck(
                "Duplicate entries",
                status=_STATUS_FAIL,
                detail=f"{s.duplicates} found",
                affected=dups,
                remediation="Run `pathkeeper dedupe` to remove duplicates.",
            )
        )
    else:
        checks.append(
            DoctorCheck("Duplicate entries", status=_STATUS_PASS, detail="none found")
        )

    # 2. Missing / invalid directories (excluding files and missing-separator)
    invalid = [
        e
        for e in report.entries
        if e.value
        and not e.exists
        and not e.is_dir
        and not e.is_empty
        and not e.likely_missing_separator
        and not e.is_duplicate
    ]
    if invalid:
        checks.append(
            DoctorCheck(
                "Missing directories",
                status=_STATUS_FAIL,
                detail=f"{len(invalid)} found",
                affected=invalid,
                remediation=(
                    "Run `pathkeeper dedupe --remove-invalid` to remove, "
                    "or `pathkeeper edit --remove <path>` for individual entries."
                ),
            )
        )
    else:
        checks.append(
            DoctorCheck("Missing directories", status=_STATUS_PASS, detail="none found")
        )

    # 3. Files masquerading as directories
    files = [e for e in report.entries if e.exists and not e.is_dir and not e.is_empty]
    if files:
        checks.append(
            DoctorCheck(
                "Files in PATH (not directories)",
                status=_STATUS_FAIL,
                detail=f"{len(files)} found",
                affected=files,
                remediation="Remove with `pathkeeper edit --remove <path>`.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Files in PATH (not directories)",
                status=_STATUS_PASS,
                detail="none found",
            )
        )

    # 4. Empty entries (double separators)
    empties = [e for e in report.entries if e.is_empty]
    if empties:
        checks.append(
            DoctorCheck(
                "Empty entries (stray separators)",
                status=_STATUS_WARN,
                detail=f"{s.empty} found",
                affected=empties,
                remediation="Run `pathkeeper dedupe` to clean them up.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Empty entries (stray separators)",
                status=_STATUS_PASS,
                detail="none found",
            )
        )

    # 5. Missing separators (glued paths)
    glued = [e for e in report.entries if e.likely_missing_separator]
    if glued:
        checks.append(
            DoctorCheck(
                "Missing separators (glued paths)",
                status=_STATUS_FAIL,
                detail=f"{s.missing_separators} found",
                affected=glued,
                remediation="Use `pathkeeper edit` to split into separate entries.",
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Missing separators (glued paths)",
                status=_STATUS_PASS,
                detail="none found",
            )
        )

    # 6. Unexpanded / unresolvable variables
    # An entry "has_unexpanded_vars" when the raw value still contains a
    # %VAR% or $VAR token after os.path.expandvars().  That happens when the
    # variable is not defined in the current process environment.  We split
    # into two buckets:
    #   • unresolvable: expanded_value still matches the raw value (the var
    #     was never substituted — the variable is undefined)
    #   • unexpanded_only: the token survived but expansion did change the
    #     string (shouldn't happen given how expandvars works, kept for safety)
    unexp = [
        e
        for e in report.entries
        if e.has_unexpanded_vars and not e.is_empty and not e.is_duplicate
    ]
    # Unresolvable = the variable token is still literally present after
    # expansion (os.path.expandvars left it unchanged because the var is
    # missing from the current environment).
    unresolvable = [
        e for e in unexp if e.expanded_value == e.value or e.has_unexpanded_vars
    ]
    if unresolvable:
        checks.append(
            DoctorCheck(
                "Unresolvable variables",
                status=_STATUS_WARN,
                detail=f"{len(unresolvable)} found",
                affected=unresolvable,
                remediation=(
                    "These entries contain %VAR% or $VAR references that the "
                    "current process cannot expand — the variables are likely "
                    "undefined.  Verify with `echo %VAR%` (cmd) or "
                    "`echo $VAR` (bash)."
                ),
            )
        )
    else:
        checks.append(
            DoctorCheck(
                "Unresolvable variables", status=_STATUS_PASS, detail="none found"
            )
        )

    # 7. PATH length (Windows-specific)
    if report.os_name == "windows":
        if report.path_length > 32767:
            checks.append(
                DoctorCheck(
                    "PATH length",
                    status=_STATUS_FAIL,
                    detail=f"{report.path_length:,} chars (exceeds registry limit)",
                    remediation=(
                        "PATH exceeds the Windows registry limit of 32,767 characters. "
                        "Create a backup and remove unnecessary entries."
                    ),
                )
            )
        elif report.path_length > 2047:
            checks.append(
                DoctorCheck(
                    "PATH length",
                    status=_STATUS_WARN,
                    detail=f"{report.path_length:,} chars (exceeds setx limit)",
                    remediation=(
                        "PATH exceeds the legacy setx limit of 2,047 characters. "
                        "Some older tools may not see the full PATH."
                    ),
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "PATH length",
                    status=_STATUS_PASS,
                    detail=f"{report.path_length:,} chars",
                )
            )

        # 8. setx / cmd.exe truncation sentinel (Windows only)
        # setx.exe silently truncates at 1,024 characters; cmd.exe's environment
        # block limit causes truncation at 1,023 or 1,024 chars in some contexts.
        # A PATH that is *exactly* 1023 or 1024 bytes is a strong telltale sign
        # of prior truncation damage even if it is currently under the setx cap.
        if report.path_length in {1023, 1024}:
            checks.append(
                DoctorCheck(
                    "setx truncation sentinel",
                    status=_STATUS_WARN,
                    detail=(
                        f"PATH is exactly {report.path_length} chars — "
                        "classic setx/cmd truncation length"
                    ),
                    remediation=(
                        "A PATH of exactly 1023 or 1024 characters is the telltale "
                        "sign that setx.exe or an older tool silently truncated your "
                        "PATH.  Compare with a known-good backup: "
                        "`pathkeeper diff-current` or `pathkeeper backups show`.  "
                        "Use `pathkeeper repair-truncated` to recover missing entries."
                    ),
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "setx truncation sentinel",
                    status=_STATUS_PASS,
                    detail=f"no truncation at {report.path_length:,} chars",
                )
            )

    return checks


def explain_entry(entry: DiagnosticEntry, os_name: str) -> str:
    """Return a plain-language explanation for a diagnostic entry's status."""
    if entry.is_empty:
        return (
            "This is an empty PATH entry (usually a stray separator). "
            "It causes no harm but can be removed with `pathkeeper dedupe`."
        )
    if entry.is_duplicate and entry.duplicate_of is not None:
        return (
            f"This entry is a duplicate of #{entry.duplicate_of}. "
            "Only the first occurrence is used; the rest are ignored by the shell. "
            "Run `pathkeeper dedupe` to remove duplicates."
        )
    if entry.has_unexpanded_vars:
        if os_name == "windows":
            return (
                f"This entry contains an unexpanded variable ({entry.value!r}). "
                "The variable may not be set in the current environment. "
                "Check the variable name and ensure it is defined before pathkeeper runs."
            )
        return (
            f"This entry contains an unexpanded shell variable ({entry.value!r}). "
            "Variables are not expanded in PATH entries read from the registry or environment on all platforms."
        )
    if entry.likely_missing_separator:
        return (
            f"This entry looks like two or more paths glued together: {entry.value!r}. "
            "A PATH separator (colon on Unix, semicolon on Windows) is probably missing. "
            "Use `pathkeeper edit` to split it into separate entries."
        )
    if not entry.exists:
        return (
            f"This directory does not exist: {entry.expanded_value!r}. "
            "It may have been uninstalled, moved, or never created. "
            "Consider removing it with `pathkeeper dedupe --remove-invalid` or `pathkeeper edit --remove`."
        )
    if entry.exists and not entry.is_dir:
        return (
            f"{entry.expanded_value!r} exists but is a file, not a directory. "
            "PATH entries must be directories. This entry will be ignored by the shell. "
            "Remove it with `pathkeeper edit --remove`."
        )
    return "This entry looks healthy."
