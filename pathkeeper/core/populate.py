from __future__ import annotations

import glob
import os
import re
import tomllib
from collections import defaultdict
from pathlib import Path

from pathkeeper.config import AppConfig, catalog_path
from pathkeeper.core.diagnostics import canonicalize_entry
from pathkeeper.models import CatalogTool, PopulateMatch


def load_catalog(config: AppConfig) -> list[CatalogTool]:
    catalog_files = [catalog_path()]
    if config.populate.extra_catalog:
        catalog_files.append(Path(config.populate.extra_catalog).expanduser())
    tools: list[CatalogTool] = []
    for path in catalog_files:
        if not path.exists():
            continue
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("tools", []):
            tools.append(
                CatalogTool(
                    name=str(item["name"]),
                    category=str(item["category"]),
                    os_name=str(item["os"]),
                    patterns=[str(pattern) for pattern in item["patterns"]],
                )
            )
    return tools


def _expand_pattern(pattern: str) -> str:
    return os.path.expanduser(os.path.expandvars(pattern))


def _split_path_parts(candidate: str) -> tuple[str, ...]:
    normalized = candidate.replace("\\", "/")
    return tuple(part for part in normalized.split("/") if part)


def _parse_dotted_version(value: str) -> tuple[int, ...] | None:
    text = value.strip().lstrip("vV")
    if not text:
        return None
    if "." in text:
        parts = text.split(".")
        if all(part.isdigit() for part in parts):
            return tuple(int(part) for part in parts)
        return None
    if not text.isdigit():
        return None
    if text.startswith("3") and len(text) in {2, 3}:
        return (3, int(text[1:]))
    return (int(text),)


def _python_version(candidate: str) -> tuple[int, ...] | None:
    for part in reversed(_split_path_parts(candidate)):
        match = re.fullmatch(r"(?i)python(?P<version>\d+(?:\.\d+)*)", part)
        if match is not None:
            return _parse_dotted_version(match.group("version"))
    return None


def _node_version(candidate: str) -> tuple[int, ...] | None:
    for part in reversed(_split_path_parts(candidate)):
        match = re.fullmatch(r"(?i)v?(?P<version>\d+\.\d+(?:\.\d+)*)", part)
        if match is not None:
            return _parse_dotted_version(match.group("version"))
    return None


def _java_version(candidate: str) -> tuple[int, ...] | None:
    for part in reversed(_split_path_parts(candidate)):
        match = re.fullmatch(r"(?i)(?:jdk|jre)[-_]?(?P<version>\d+(?:\.\d+)*)", part)
        if match is not None:
            return _parse_dotted_version(match.group("version"))
    return None


def _generic_version(candidate: str) -> tuple[int, ...] | None:
    for part in reversed(_split_path_parts(candidate)):
        if re.fullmatch(r"(?i)v?\d+(?:\.\d+)*", part):
            parsed = _parse_dotted_version(part)
            if parsed is not None:
                return parsed
    return None


def _candidate_version(tool_name: str, candidate: str) -> tuple[int, ...] | None:
    if tool_name == "Python":
        return _python_version(candidate)
    if tool_name == "Node.js":
        return _node_version(candidate)
    if tool_name == "Java":
        return _java_version(candidate)
    return _generic_version(candidate)


def _prefer_latest_versions(matches: list[PopulateMatch]) -> list[PopulateMatch]:
    grouped: dict[tuple[str, str], list[tuple[tuple[int, ...], PopulateMatch]]] = (
        defaultdict(list)
    )
    unversioned: list[PopulateMatch] = []
    for match in matches:
        version = _candidate_version(match.name, match.path)
        if version is None:
            unversioned.append(match)
            continue
        grouped[(match.category, match.name)].append((version, match))
    selected = list(unversioned)
    for versioned_matches in grouped.values():
        latest = max(version for version, _match in versioned_matches)
        selected.extend(
            match for version, match in versioned_matches if version == latest
        )
    return sorted(
        selected, key=lambda item: (item.category, item.name, item.path.casefold())
    )


def discover_tools(
    catalog: list[CatalogTool],
    existing_entries: list[str],
    *,
    os_name: str,
    category: str | None = None,
) -> list[PopulateMatch]:
    existing = {canonicalize_entry(item, os_name) for item in existing_entries}
    matches: dict[str, PopulateMatch] = {}
    for tool in catalog:
        if tool.os_name not in {os_name, "all"}:
            continue
        if category and tool.category != category:
            continue
        for pattern in tool.patterns:
            for candidate in glob.glob(_expand_pattern(pattern)):
                if not Path(candidate).is_dir():
                    continue
                canonical = canonicalize_entry(candidate, os_name)
                if canonical in existing or canonical in matches:
                    continue
                matches[canonical] = PopulateMatch(
                    name=tool.name, category=tool.category, path=candidate
                )
    return _prefer_latest_versions(list(matches.values()))


def group_matches(matches: list[PopulateMatch]) -> dict[str, list[PopulateMatch]]:
    grouped: dict[str, list[PopulateMatch]] = defaultdict(list)
    for match in matches:
        grouped[match.category].append(match)
    return dict(sorted(grouped.items(), key=lambda item: item[0].casefold()))
