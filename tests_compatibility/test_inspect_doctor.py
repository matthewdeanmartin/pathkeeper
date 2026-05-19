"""T3 — inspect and doctor subcommands."""

from __future__ import annotations

import json


def test_inspect(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "inspect"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_inspect_json(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "inspect", "--json"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "entries" in payload
    assert "summary" in payload


def test_inspect_only_invalid(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "inspect", "--only-invalid"], env_extra={"PATHX": pathx}
    )
    assert result.returncode == 0


def test_inspect_only_dupes(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "inspect", "--only-dupes"], env_extra={"PATHX": pathx}
    )
    assert result.returncode == 0


def test_doctor(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "doctor"], env_extra={"PATHX": pathx})
    assert result.returncode == 0


def test_doctor_json(runner, pathx: str) -> None:
    result = runner(["--var", "PATHX", "doctor", "--json"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert "checks" in payload
    assert "summary" in payload


def test_doctor_explain(runner, pathx: str) -> None:
    result = runner(
        ["--var", "PATHX", "doctor", "--explain"], env_extra={"PATHX": pathx}
    )
    assert result.returncode == 0


def test_doctor_json_valid_structure(runner, pathx: str) -> None:
    """Each check entry must have the required fields."""
    result = runner(["--var", "PATHX", "doctor", "--json"], env_extra={"PATHX": pathx})
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    for check in payload["checks"]:
        assert "name" in check
        assert "status" in check


def test_inspect_path_var(runner, dirs) -> None:
    """inspect should also work with the real PATH variable (r/o, no --var)."""
    result = runner(["inspect"])
    assert result.returncode == 0


def test_doctor_path_var(runner) -> None:
    result = runner(["doctor"])
    assert result.returncode == 0
