"""T8 — edit subcommand (non-interactive flag-driven and interactive via stdin)."""
from __future__ import annotations


def test_edit_add_dry_run(runner, pathx: str, dirs) -> None:
    _a, _b, _c, d = dirs
    result = runner(
        ["--var", "PATHX", "edit", "--add", d, "--dry-run"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_edit_add_force(runner, pathx: str, dirs) -> None:
    _a, _b, _c, d = dirs
    result = runner(
        ["--var", "PATHX", "edit", "--add", d, "--force"],
        env_extra={"PATHX": pathx},
    )
    assert result.returncode == 0


def test_edit_interactive_quit(runner, pathx: str) -> None:
    """Entering 'q' at the interactive edit prompt should exit cleanly."""
    result = runner(
        ["--var", "PATHX", "edit"],
        env_extra={"PATHX": pathx},
        # answer the scope prompt then quit the editor
        input_text="user\nq\n",
    )
    assert result.returncode == 0


def test_edit_interactive_preview_then_quit(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "edit"],
        env_extra={"PATHX": pathx},
        input_text="user\np\nq\n",
    )
    assert result.returncode == 0


def test_edit_interactive_add_then_quit(runner, pathx: str, dirs) -> None:
    _a, _b, _c, d = dirs
    result = runner(
        ["--var", "PATHX", "edit"],
        env_extra={"PATHX": pathx},
        input_text=f"user\na {d}\nq\n",
    )
    assert result.returncode == 0
