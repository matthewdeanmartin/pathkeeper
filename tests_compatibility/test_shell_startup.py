"""shell-startup subcommand tests (dry-run only)."""

from __future__ import annotations


def test_shell_startup_dry_run_bash(runner, tmp_path) -> None:
    rc = tmp_path / ".bashrc"
    rc.write_text("# existing\n", encoding="utf-8")
    result = runner(
        ["shell-startup", "--shell", "bash", "--rc-file", str(rc), "--dry-run"]
    )
    assert result.returncode == 0
    # Dry-run must not modify the file
    assert rc.read_text(encoding="utf-8") == "# existing\n"


def test_shell_startup_dry_run_powershell(runner, tmp_path) -> None:
    rc = tmp_path / "profile.ps1"
    rc.write_text("# ps1\n", encoding="utf-8")
    result = runner(
        ["shell-startup", "--shell", "powershell", "--rc-file", str(rc), "--dry-run"]
    )
    assert result.returncode == 0
    assert rc.read_text(encoding="utf-8") == "# ps1\n"


def test_shell_startup_remove_dry_run(runner, tmp_path) -> None:
    """--remove --dry-run against a file without the marker should exit 0 cleanly."""
    rc = tmp_path / ".bashrc"
    rc.write_text("# no marker\n", encoding="utf-8")
    result = runner(
        [
            "shell-startup",
            "--shell",
            "bash",
            "--rc-file",
            str(rc),
            "--dry-run",
            "--remove",
        ]
    )
    assert result.returncode == 0
    assert rc.read_text(encoding="utf-8") == "# no marker\n"
