from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from pathkeeper.core.locate import locate_executable


def test_locate_executable_python_fallback(tmp_path: Path) -> None:
    # Create a dummy executable
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    exe_file = bin_dir / "mytool"
    if os.name == "nt":
        exe_file = bin_dir / "mytool.exe"
    exe_file.touch()
    if os.name != "nt":
        exe_file.chmod(exe_file.stat().st_mode | 0o111)

    # Mock shutil.which to say 'rg' and 'fd' are NOT available
    with (
        patch("shutil.which", return_value=None),
        patch(
            "pathkeeper.core.locate.normalized_os_name",
            return_value="windows" if os.name == "nt" else "linux",
        ),
        patch("pathkeeper.core.locate.load_catalog", return_value=[]),
    ):
        # We search in tmp_path
        # We need to mock search_root calculation too
        results = locate_executable("mytool", find_all=True, drive=str(tmp_path))
        assert any(
            str(r).endswith("mytool.exe" if os.name == "nt" else "mytool")
            for r in results
        )


def test_locate_executable_likely_locations(tmp_path: Path) -> None:
    # Create a dummy executable in a "likely" location
    likely_dir = tmp_path / "likely"
    likely_dir.mkdir()
    exe_file = likely_dir / "git.exe" if os.name == "nt" else likely_dir / "git"
    exe_file.touch()
    if os.name != "nt":
        exe_file.chmod(exe_file.stat().st_mode | 0o111)

    # Mock catalog
    mock_tool = MagicMock()
    mock_tool.name = "Git"
    mock_tool.executables = ["git"]
    mock_tool.patterns = [str(likely_dir / "*")]

    with (
        patch("pathkeeper.core.locate.load_catalog", return_value=[mock_tool]),
        patch("pathkeeper.core.locate._expand_pattern", side_effect=lambda x: x),
    ):
        results = locate_executable("git", find_all=False)
        assert any(
            str(r).endswith("git.exe" if os.name == "nt" else "git") for r in results
        )
