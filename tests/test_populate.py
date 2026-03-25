from __future__ import annotations

from pathlib import Path

import pytest

from pathkeeper.core.populate import discover_tools
from pathkeeper.models import CatalogTool


def test_discover_tools_keeps_latest_python_version_with_scripts(
    tmp_path: Path,
) -> None:
    python311 = tmp_path / "Python311"
    python311_scripts = python311 / "Scripts"
    python313 = tmp_path / "Python313"
    python313_scripts = python313 / "Scripts"
    python311_scripts.mkdir(parents=True)
    python313_scripts.mkdir(parents=True)
    catalog = [
        CatalogTool(
            name="Python",
            category="Programming Languages",
            os_name="windows",
            patterns=[
                str(tmp_path / "Python3*"),
                str(tmp_path / "Python3*" / "Scripts"),
            ],
        )
    ]

    matches = discover_tools(catalog, [], os_name="windows")

    programming_matches = [
        match for match in matches if match.category == "Programming Languages"
    ]

    assert [match.path for match in programming_matches] == [
        str(python313),
        str(python313_scripts),
    ]


def test_discover_tools_keeps_latest_node_version(tmp_path: Path) -> None:
    node14 = tmp_path / ".nvm" / "versions" / "node" / "v14.21.3" / "bin"
    node18 = tmp_path / ".nvm" / "versions" / "node" / "v18.16.0" / "bin"
    node14.mkdir(parents=True)
    node18.mkdir(parents=True)
    catalog = [
        CatalogTool(
            name="Node.js",
            category="Programming Languages",
            os_name="all",
            patterns=[str(tmp_path / ".nvm" / "versions" / "node" / "*" / "bin")],
        )
    ]

    matches = discover_tools(catalog, [], os_name="windows")

    programming_matches = [
        match for match in matches if match.category == "Programming Languages"
    ]

    assert [match.path for match in programming_matches] == [str(node18)]


def test_discover_tools_adds_missing_unix_baseline_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = [tmp_path / "usr-local-bin", tmp_path / "usr-bin"]
    for path in baseline:
        path.mkdir()

    from pathkeeper.core import populate as populate_mod

    monkeypatch.setattr(
        populate_mod,
        "_baseline_paths",
        lambda _os_name: [str(path) for path in baseline],
    )

    matches = discover_tools([], [str(baseline[0])], os_name="linux")

    assert [(match.category, match.name, match.path) for match in matches] == [
        ("Baseline", "Standard commands", str(baseline[1]))
    ]


def test_discover_tools_adds_missing_windows_baseline_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = [
        tmp_path / "Windows" / "system32",
        tmp_path / "Windows",
        tmp_path / "Windows" / "System32" / "Wbem",
    ]
    for path in baseline:
        path.mkdir(parents=True, exist_ok=True)

    from pathkeeper.core import populate as populate_mod

    monkeypatch.setattr(
        populate_mod,
        "_baseline_paths",
        lambda _os_name: [str(path) for path in baseline],
    )

    matches = discover_tools([], [str(baseline[1])], os_name="windows")

    assert [(match.category, match.name, match.path) for match in matches] == [
        ("Baseline", "Standard commands", str(baseline[0])),
        ("Baseline", "Standard commands", str(baseline[2])),
    ]
