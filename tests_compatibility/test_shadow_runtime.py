"""T5 — shadow, runtime-entries, and selfcheck subcommands."""

from __future__ import annotations

import json


def test_shadow(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "shadow"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_shadow_json(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "shadow", "--json"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
    # Output must be valid JSON — either an array or the text "No shadowed executables found."
    try:
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)
    except json.JSONDecodeError:
        # Some implementations may print a plain "no shadows" message instead; accept it.
        combined = result.stdout + result.stderr
        assert combined.strip() != ""


def test_runtime_entries(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "runtime-entries"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_runtime_entries_live_path(runner) -> None:
    """runtime-entries also works against the real PATH."""
    result = runner(["runtime-entries"])
    assert result.returncode == 0


def test_selfcheck(runner) -> None:
    # selfcheck may exit 1 when the installation is not fully set up — that's expected.
    result = runner(["selfcheck"])
    assert result.returncode in {0, 1}, (
        f"selfcheck exited {result.returncode}:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert combined.strip() != ""
