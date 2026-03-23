from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Scope(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ALL = "all"

    @classmethod
    def from_value(cls, value: str) -> Scope:
        return cls(value)


@dataclass(frozen=True)
class PathSnapshot:
    system_path: list[str]
    user_path: list[str]
    system_path_raw: str
    user_path_raw: str

    def entries_for_scope(self, scope: Scope) -> list[str]:
        if scope is Scope.SYSTEM:
            return list(self.system_path)
        if scope is Scope.USER:
            return list(self.user_path)
        return [*self.system_path, *self.user_path]

    def raw_for_scope(self, scope: Scope) -> str:
        if scope is Scope.SYSTEM:
            return self.system_path_raw
        if scope is Scope.USER:
            return self.user_path_raw
        if self.system_path_raw and self.user_path_raw:
            return f"{self.system_path_raw};{self.user_path_raw}"
        return self.system_path_raw or self.user_path_raw

    def with_scope_entries(
        self, scope: Scope, entries: list[str], raw: str
    ) -> PathSnapshot:
        if scope is Scope.SYSTEM:
            return PathSnapshot(entries, list(self.user_path), raw, self.user_path_raw)
        if scope is Scope.USER:
            return PathSnapshot(
                list(self.system_path), entries, self.system_path_raw, raw
            )
        raise ValueError("Cannot replace all scopes at once")


@dataclass(frozen=True)
class BackupRecord:
    version: int
    timestamp: datetime
    hostname: str
    os_name: str
    tag: str
    note: str
    system_path: list[str]
    user_path: list[str]
    system_path_raw: str
    user_path_raw: str
    source_file: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "timestamp": self.timestamp.isoformat().replace("+00:00", "Z"),
            "hostname": self.hostname,
            "os": self.os_name,
            "tag": self.tag,
            "note": self.note,
            "system_path": self.system_path,
            "user_path": self.user_path,
            "system_path_raw": self.system_path_raw,
            "user_path_raw": self.user_path_raw,
        }

    @property
    def snapshot(self) -> PathSnapshot:
        return PathSnapshot(
            system_path=list(self.system_path),
            user_path=list(self.user_path),
            system_path_raw=self.system_path_raw,
            user_path_raw=self.user_path_raw,
        )


@dataclass(frozen=True)
class DiagnosticEntry:
    index: int
    value: str
    scope: Scope
    exists: bool
    is_dir: bool
    is_duplicate: bool
    duplicate_of: int | None
    is_empty: bool
    has_unexpanded_vars: bool
    expanded_value: str


@dataclass(frozen=True)
class DiagnosticSummary:
    total: int
    valid: int
    invalid: int
    duplicates: int
    empty: int
    files: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiagnosticReport:
    entries: list[DiagnosticEntry]
    summary: DiagnosticSummary
    os_name: str
    path_length: int


@dataclass(frozen=True)
class PathDiff:
    added: list[str]
    removed: list[str]
    reordered: list[str]


@dataclass(frozen=True)
class CleanupResult:
    original: list[str]
    cleaned: list[str]
    removed_duplicates: list[str]
    removed_invalid: list[str]
    removed_empty: list[str]


@dataclass(frozen=True)
class TruncatedPathCandidate:
    path: str
    source: str


@dataclass(frozen=True)
class TruncatedPathRepair:
    display_index: int
    scope_index: int
    scope: Scope
    value: str
    candidates: list[TruncatedPathCandidate]


@dataclass(frozen=True)
class CatalogTool:
    name: str
    category: str
    os_name: str
    patterns: list[str]


@dataclass(frozen=True)
class PopulateMatch:
    name: str
    category: str
    path: str


@dataclass
class EditSessionState:
    original: list[str]
    current: list[str]
    history: list[list[str]] = field(default_factory=list)
