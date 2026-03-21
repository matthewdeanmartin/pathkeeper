from __future__ import annotations

import glob
import os
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
                matches[canonical] = PopulateMatch(name=tool.name, category=tool.category, path=candidate)
    return sorted(matches.values(), key=lambda item: (item.category, item.name, item.path.casefold()))


def group_matches(matches: list[PopulateMatch]) -> dict[str, list[PopulateMatch]]:
    grouped: dict[str, list[PopulateMatch]] = defaultdict(list)
    for match in matches:
        grouped[match.category].append(match)
    return dict(sorted(grouped.items(), key=lambda item: item[0].casefold()))

