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


def canonicalize_entry(entry: str, os_name: str) -> str:
    value = expand_entry(entry)
    if os_name == "windows":
        normalized = value.replace("/", "\\").rstrip("\\")
        return normalized.casefold()
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
    if report.summary.warnings:
        recommendations.append(
            "Create a backup now and consider restoring a healthier snapshot."
        )
    if not recommendations:
        recommendations.append("No obvious PATH issues were detected.")
    return recommendations


def explain_entry(entry: "DiagnosticEntry", os_name: str) -> str:
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
