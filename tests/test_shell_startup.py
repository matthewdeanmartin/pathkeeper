"""Tests for shell-startup command: injection, removal, dry-run, fish support."""

from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.cli import (
    _SHELL_STARTUP_MARKER,
    _detect_shell_rc,
    _shell_startup_already_present,
    _shell_startup_backup_line,
    _shell_startup_rc_for,
)

# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------


def test_shell_startup_backup_line_bash() -> None:
    line = _shell_startup_backup_line("bash")
    assert "pathkeeper backup --quiet --tag auto" in line
    assert _SHELL_STARTUP_MARKER in line
    assert "<#" not in line  # not PowerShell syntax


def test_shell_startup_backup_line_zsh() -> None:
    line = _shell_startup_backup_line("zsh")
    assert "pathkeeper backup --quiet --tag auto" in line
    assert _SHELL_STARTUP_MARKER in line
    assert "<#" not in line


def test_shell_startup_backup_line_fish() -> None:
    line = _shell_startup_backup_line("fish")
    assert "pathkeeper backup --quiet --tag auto" in line
    assert _SHELL_STARTUP_MARKER in line
    assert "<#" not in line  # fish uses # not <# #>


def test_shell_startup_backup_line_powershell() -> None:
    line = _shell_startup_backup_line("powershell")
    assert "pathkeeper backup --quiet --tag auto" in line
    assert _SHELL_STARTUP_MARKER in line
    assert "<#" in line
    assert "#>" in line


def test_shell_startup_already_present_true() -> None:
    text = f"some lines\n{_SHELL_STARTUP_MARKER}\nmore\n"
    assert _shell_startup_already_present(text) is True


def test_shell_startup_already_present_false() -> None:
    text = "export PATH=$PATH:/usr/bin\n"
    assert _shell_startup_already_present(text) is False


def test_shell_startup_already_present_empty_file() -> None:
    assert _shell_startup_already_present("") is False


def test_shell_startup_rc_for_bash() -> None:
    shell_name, rc_file = _shell_startup_rc_for("bash")
    assert shell_name == "bash"
    assert rc_file.endswith(".bashrc")


def test_shell_startup_rc_for_zsh() -> None:
    shell_name, rc_file = _shell_startup_rc_for("zsh")
    assert shell_name == "zsh"
    assert rc_file.endswith(".zshrc")


def test_shell_startup_rc_for_fish() -> None:
    shell_name, rc_file = _shell_startup_rc_for("fish")
    assert shell_name == "fish"
    assert "config.fish" in rc_file
    assert ".config/fish" in rc_file or ".config\\fish" in rc_file


def test_shell_startup_rc_for_powershell() -> None:
    shell_name, rc_file = _shell_startup_rc_for("powershell")
    assert shell_name == "powershell"
    assert "PowerShell_profile.ps1" in rc_file


def test_shell_startup_rc_for_pwsh_alias() -> None:
    shell_name, _rc_file = _shell_startup_rc_for("pwsh")
    assert shell_name == "powershell"


def test_shell_startup_rc_for_unknown_shell_raises() -> None:
    from pathkeeper.errors import PathkeeperError

    with pytest.raises(PathkeeperError, match="Unknown shell"):
        _shell_startup_rc_for("csh")


def test_detect_shell_rc_bash(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/bin/bash")
    result = _detect_shell_rc()
    assert result is not None
    shell_name, rc_file = result
    assert shell_name == "bash"
    assert ".bashrc" in rc_file


def test_detect_shell_rc_zsh(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/zsh")
    result = _detect_shell_rc()
    assert result is not None
    shell_name, rc_file = result
    assert shell_name == "zsh"
    assert ".zshrc" in rc_file


def test_detect_shell_rc_fish(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("SHELL", "/usr/bin/fish")
    result = _detect_shell_rc()
    assert result is not None
    shell_name, rc_file = result
    assert shell_name == "fish"
    assert "config.fish" in rc_file


def test_detect_shell_rc_no_shell_env_falls_back_to_powershell(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("SHELL", raising=False)
    result = _detect_shell_rc()
    assert result is not None
    shell_name, _rc_file = result
    assert shell_name == "powershell"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_shell_startup_bash_injects_line(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("export PATH=$PATH:/usr/bin\n", encoding="utf-8")
    exit_code = cli.run(["shell-startup", "--shell", "bash", "--rc-file", str(rc_file)])
    assert exit_code == 0
    content = rc_file.read_text(encoding="utf-8")
    assert _SHELL_STARTUP_MARKER in content
    assert "pathkeeper backup --quiet --tag auto" in content
    output = capsys.readouterr().out
    assert "Added startup backup" in output


def test_shell_startup_fish_injects_correct_syntax(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / "config.fish"
    rc_file.write_text("set -x PATH /usr/bin $PATH\n", encoding="utf-8")
    exit_code = cli.run(["shell-startup", "--shell", "fish", "--rc-file", str(rc_file)])
    assert exit_code == 0
    content = rc_file.read_text(encoding="utf-8")
    assert _SHELL_STARTUP_MARKER in content
    assert "pathkeeper backup --quiet --tag auto" in content
    # Fish uses # comments, not <# #>
    assert "<#" not in content
    output = capsys.readouterr().out
    assert "config.fish" in output


def test_shell_startup_powershell_injects_block_comment(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / "Microsoft.PowerShell_profile.ps1"
    rc_file.write_text("# existing profile\n", encoding="utf-8")
    exit_code = cli.run(
        ["shell-startup", "--shell", "powershell", "--rc-file", str(rc_file)]
    )
    assert exit_code == 0
    content = rc_file.read_text(encoding="utf-8")
    assert _SHELL_STARTUP_MARKER in content
    assert "<#" in content
    assert "#>" in content


def test_shell_startup_idempotent_does_not_duplicate(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("", encoding="utf-8")
    cli.run(["shell-startup", "--shell", "bash", "--rc-file", str(rc_file)])
    capsys.readouterr()
    exit_code = cli.run(["shell-startup", "--shell", "bash", "--rc-file", str(rc_file)])
    output = capsys.readouterr().out
    assert exit_code == 0
    # Marker should appear exactly once
    content = rc_file.read_text(encoding="utf-8")
    assert content.count(_SHELL_STARTUP_MARKER) == 1
    assert "already present" in output


def test_shell_startup_remove_cleans_up_line(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("export PATH=$PATH:/usr/bin\n", encoding="utf-8")
    cli.run(["shell-startup", "--shell", "bash", "--rc-file", str(rc_file)])
    capsys.readouterr()
    exit_code = cli.run(
        ["shell-startup", "--shell", "bash", "--rc-file", str(rc_file), "--remove"]
    )
    assert exit_code == 0
    content = rc_file.read_text(encoding="utf-8")
    assert _SHELL_STARTUP_MARKER not in content
    output = capsys.readouterr().out
    assert "Removed" in output


def test_shell_startup_remove_when_not_present_is_noop(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("export PATH=$PATH:/usr/bin\n", encoding="utf-8")
    exit_code = cli.run(
        ["shell-startup", "--shell", "bash", "--rc-file", str(rc_file), "--remove"]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Nothing to remove" in output
    # File unchanged
    assert _SHELL_STARTUP_MARKER not in rc_file.read_text(encoding="utf-8")


def test_shell_startup_dry_run_does_not_write(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    rc_file.write_text("", encoding="utf-8")
    exit_code = cli.run(
        ["shell-startup", "--shell", "bash", "--rc-file", str(rc_file), "--dry-run"]
    )
    assert exit_code == 0
    content = rc_file.read_text(encoding="utf-8")
    assert _SHELL_STARTUP_MARKER not in content
    output = capsys.readouterr().out
    assert "dry-run" in output.lower() or "Dry run" in output


def test_shell_startup_creates_missing_rc_file(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / "subdir" / ".bashrc"
    # File does not exist; parent dir also doesn't exist
    assert not rc_file.exists()
    exit_code = cli.run(["shell-startup", "--shell", "bash", "--rc-file", str(rc_file)])
    assert exit_code == 0
    assert rc_file.exists()
    assert _SHELL_STARTUP_MARKER in rc_file.read_text(encoding="utf-8")


def test_shell_startup_dry_run_remove_does_not_write(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".bashrc"
    line = _shell_startup_backup_line("bash")
    rc_file.write_text(f"{line}\n", encoding="utf-8")
    exit_code = cli.run(
        [
            "shell-startup",
            "--shell",
            "bash",
            "--rc-file",
            str(rc_file),
            "--remove",
            "--dry-run",
        ]
    )
    assert exit_code == 0
    # Marker still present because dry-run
    assert _SHELL_STARTUP_MARKER in rc_file.read_text(encoding="utf-8")
    output = capsys.readouterr().out
    assert "dry-run" in output.lower() or "Dry run" in output


def test_shell_startup_fish_reload_hint(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / "config.fish"
    rc_file.write_text("", encoding="utf-8")
    cli.run(["shell-startup", "--shell", "fish", "--rc-file", str(rc_file)])
    output = capsys.readouterr().out
    assert "config.fish" in output  # fish-specific reload hint


def test_shell_startup_zsh_reload_hint(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    rc_file = tmp_path / ".zshrc"
    rc_file.write_text("", encoding="utf-8")
    cli.run(["shell-startup", "--shell", "zsh", "--rc-file", str(rc_file)])
    output = capsys.readouterr().out
    assert ".zshrc" in output
