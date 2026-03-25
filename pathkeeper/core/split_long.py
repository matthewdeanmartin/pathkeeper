from __future__ import annotations

import re
from dataclasses import dataclass

from pathkeeper.errors import PathkeeperError
from pathkeeper.models import PathSnapshot, Scope

_PLAIN_WINDOWS_VAR_PATTERN = re.compile(r"^%([A-Za-z_][A-Za-z0-9_]*)%$")
_VALID_VAR_PREFIX_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class SplitLongPlan:
    scope: Scope
    original_entries: list[str]
    flattened_entries: list[str]
    updated_entries: list[str]
    original_raw: str
    updated_raw: str
    helper_vars: dict[str, str]
    preserved_env_vars: dict[str, str]
    removed_helper_vars: tuple[str, ...]
    max_length: int
    chunk_length: int
    var_prefix: str

    @property
    def changed(self) -> bool:
        return (
            self.original_raw != self.updated_raw
            or self.original_entries != self.updated_entries
            or bool(self.helper_vars)
            or bool(self.removed_helper_vars)
        )


def default_var_prefix(scope: Scope) -> str:
    if scope is Scope.SYSTEM:
        return "PK_SYSTEM_PATHS"
    if scope is Scope.USER:
        return "PK_USER_PATHS"
    raise ValueError("split-long only supports system or user scope")


def build_split_long_plan(
    snapshot: PathSnapshot,
    *,
    scope: Scope,
    os_name: str,
    environment: dict[str, str],
    max_length: int = 2047,
    chunk_length: int = 2047,
    var_prefix: str | None = None,
) -> SplitLongPlan:
    if os_name != "windows":
        raise PathkeeperError("split-long is currently supported on Windows only.")
    if scope not in {Scope.SYSTEM, Scope.USER}:
        raise PathkeeperError(
            "split-long supports only --scope system or --scope user."
        )
    if max_length < 32:
        raise PathkeeperError("--max-length must be at least 32.")
    if chunk_length < 32:
        raise PathkeeperError("--chunk-length must be at least 32.")
    prefix = (var_prefix or default_var_prefix(scope)).upper()
    if not _VALID_VAR_PREFIX_PATTERN.fullmatch(prefix):
        raise PathkeeperError(
            f"Invalid variable prefix {prefix!r}. Use letters, numbers, and underscores."
        )

    original_entries = snapshot.entries_for_scope(scope)
    original_raw = snapshot.raw_for_scope(scope)
    existing_scope_env = snapshot.env_vars_for_scope(scope)
    flattened_entries, flattened_helper_names = _flatten_managed_entries(
        original_entries, environment, prefix
    )
    managed_names = _managed_names(environment, prefix)
    if len(original_raw) <= max_length and not flattened_helper_names:
        return SplitLongPlan(
            scope=scope,
            original_entries=list(original_entries),
            flattened_entries=list(flattened_entries),
            updated_entries=list(original_entries),
            original_raw=original_raw,
            updated_raw=original_raw,
            helper_vars={},
            preserved_env_vars=dict(existing_scope_env),
            removed_helper_vars=(),
            max_length=max_length,
            chunk_length=chunk_length,
            var_prefix=prefix,
        )

    updated_entries, helper_vars = _compress_entries(
        flattened_entries,
        environment=environment,
        prefix=prefix,
        max_length=max_length,
        chunk_length=chunk_length,
    )
    updated_raw = ";".join(updated_entries)
    preserved_env_vars = {
        name: value
        for name, value in existing_scope_env.items()
        if name not in managed_names
    }
    removed_helper_vars = tuple(
        sorted(name for name in managed_names if name not in helper_vars)
    )
    updated_scope_env = dict(preserved_env_vars)
    updated_scope_env.update(helper_vars)
    return SplitLongPlan(
        scope=scope,
        original_entries=list(original_entries),
        flattened_entries=list(flattened_entries),
        updated_entries=updated_entries,
        original_raw=original_raw,
        updated_raw=updated_raw,
        helper_vars=helper_vars,
        preserved_env_vars=updated_scope_env,
        removed_helper_vars=removed_helper_vars,
        max_length=max_length,
        chunk_length=chunk_length,
        var_prefix=prefix,
    )


def apply_plan_to_snapshot(snapshot: PathSnapshot, plan: SplitLongPlan) -> PathSnapshot:
    updated = snapshot.with_scope_entries(
        plan.scope, plan.updated_entries, plan.updated_raw
    )
    return updated.with_scope_env_vars(plan.scope, plan.preserved_env_vars)


def render_plan(plan: SplitLongPlan) -> str:
    lines = [
        f"Scope: {plan.scope.value}",
        f"Original PATH length: {len(plan.original_raw):,}",
        f"Updated PATH length:  {len(plan.updated_raw):,}",
        f"Target PATH length:   {plan.max_length:,}",
    ]
    if not plan.changed:
        lines.append(
            "PATH is already within the requested length. No helper variables needed."
        )
        return "\n".join(lines)
    lines.extend(
        [
            f"Helper variables:    {len(plan.helper_vars)}",
            "",
            "Updated PATH entries:",
        ]
    )
    for index, entry in enumerate(plan.updated_entries, start=1):
        lines.append(f"  {index:>2}. {entry}")
    if plan.helper_vars:
        lines.append("")
        lines.append("Helper variable values:")
        for name, value in plan.helper_vars.items():
            entry_count = 0 if not value else len(value.split(";"))
            lines.append(
                f"  {name} = {value}  ({entry_count} entr{'y' if entry_count == 1 else 'ies'})"
            )
    if plan.removed_helper_vars:
        lines.append("")
        lines.append(
            "Old helper variables to remove: " + ", ".join(plan.removed_helper_vars)
        )
    return "\n".join(lines)


def _flatten_managed_entries(
    entries: list[str], environment: dict[str, str], prefix: str
) -> tuple[list[str], tuple[str, ...]]:
    flattened: list[str] = []
    expanded_names: list[str] = []
    managed = {name.casefold(): name for name in _managed_names(environment, prefix)}
    for entry in entries:
        match = _PLAIN_WINDOWS_VAR_PATTERN.fullmatch(entry.strip())
        if match is None:
            flattened.append(entry)
            continue
        name = managed.get(match.group(1).casefold())
        if name is None:
            flattened.append(entry)
            continue
        value = environment.get(name, "")
        expanded_names.append(name)
        if value:
            flattened.extend(value.split(";"))
    return flattened, tuple(expanded_names)


def _compress_entries(
    entries: list[str],
    *,
    environment: dict[str, str],
    prefix: str,
    max_length: int,
    chunk_length: int,
) -> tuple[list[str], dict[str, str]]:
    for keep_literal_count in range(len(entries), -1, -1):
        groups = _chunk_entries(entries[keep_literal_count:], chunk_length)
        names = _allocate_var_names(environment, prefix, len(groups))
        refs = [f"%{name}%" for name in names]
        candidate_entries = [*entries[:keep_literal_count], *refs]
        if len(";".join(candidate_entries)) <= max_length:
            helper_vars = {
                name: ";".join(group) for name, group in zip(names, groups, strict=True)
            }
            return candidate_entries, helper_vars
    names = _allocate_var_names(environment, prefix, 1)
    return [f"%{names[0]}%"], {names[0]: ";".join(entries)}


def _chunk_entries(entries: list[str], chunk_length: int) -> list[list[str]]:
    if not entries:
        return []
    groups: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    for entry in entries:
        addition = len(entry) if not current else len(entry) + 1
        if current and current_length + addition > chunk_length:
            groups.append(current)
            current = [entry]
            current_length = len(entry)
            continue
        current.append(entry)
        current_length += addition
    if current:
        groups.append(current)
    return groups


def _allocate_var_names(
    environment: dict[str, str], prefix: str, count: int
) -> list[str]:
    allocated: list[str] = []
    reserved = {
        name.casefold() for name in environment if not _is_managed_name(name, prefix)
    }
    index = 1
    while len(allocated) < count:
        candidate = f"{prefix}_{index}"
        if candidate.casefold() not in reserved:
            allocated.append(candidate)
        index += 1
    return allocated


def _managed_names(environment: dict[str, str], prefix: str) -> set[str]:
    return {name for name in environment if _is_managed_name(name, prefix)}


def _is_managed_name(name: str, prefix: str) -> bool:
    if not name.casefold().startswith((prefix + "_").casefold()):
        return False
    suffix = name[len(prefix) + 1 :]
    return suffix.isdigit()
