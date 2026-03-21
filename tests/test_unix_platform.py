from __future__ import annotations

from pathlib import Path

from pathkeeper.platform.linux import LinuxPlatform
from pathkeeper.platform.unix_common import MANAGED_MARKER


def test_linux_user_path_write_only_touches_managed_block(tmp_path: Path) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("export OTHER=value\n", encoding="utf-8")
    platform = LinuxPlatform(rc_file_override=str(rc_file), environ={"PATH": "/usr/bin"}, system_path_file=tmp_path / "environment")
    platform.write_user_path(["/opt/tool/bin", "/usr/local/bin"])
    content = rc_file.read_text(encoding="utf-8")
    assert "export OTHER=value" in content
    assert MANAGED_MARKER in content
    assert 'export PATH="/opt/tool/bin:/usr/local/bin"' in content
    assert platform.read_user_path() == ["/opt/tool/bin", "/usr/local/bin"]


def test_linux_system_path_write_preserves_non_path_lines(tmp_path: Path) -> None:
    system_file = tmp_path / "environment"
    system_file.write_text('LANG="en_US.UTF-8"\nPATH="/usr/bin"\n', encoding="utf-8")
    platform = LinuxPlatform(rc_file_override=str(tmp_path / ".bashrc"), environ={"PATH": "/usr/bin"}, system_path_file=system_file)
    platform.write_system_path(["/usr/local/bin", "/usr/bin"])
    content = system_file.read_text(encoding="utf-8")
    assert 'LANG="en_US.UTF-8"' in content
    assert 'PATH="/usr/local/bin:/usr/bin"' in content
