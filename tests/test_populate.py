from __future__ import annotations

from pathlib import Path

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

    assert [match.path for match in matches] == [str(python313), str(python313_scripts)]


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

    assert [match.path for match in matches] == [str(node18)]
