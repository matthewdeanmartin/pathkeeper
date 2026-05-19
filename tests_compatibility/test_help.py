"""T1 — version and help for all subcommands."""
from __future__ import annotations

import pytest


SUBCOMMANDS = [
    "inspect",
    "doctor",
    "backup",
    "backups",
    "restore",
    "dedupe",
    "populate",
    "repair-truncated",
    "split-long",
    "edit",
    "schedule",
    "diff",
    "diff-current",
    "shadow",
    "runtime-entries",
    "shell-startup",
    "selfcheck",
    "locate",
]

SUBCOMMANDS_WITH_SUBSUB = {
    "backups": ["list", "show"],
    "schedule": ["install", "remove", "status"],
}


def test_version(runner) -> None:
    result = runner(["--version"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert combined.strip() != ""


def test_root_help(runner) -> None:
    result = runner(["--help"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert len(combined) > 50


@pytest.mark.parametrize("sub", SUBCOMMANDS)
def test_subcommand_help(runner, sub: str) -> None:
    result = runner([sub, "--help"])
    assert result.returncode == 0, (
        f"--help for '{sub}' exited {result.returncode}:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert len(combined) > 10


@pytest.mark.parametrize("sub,subsub", [
    (sub, ss)
    for sub, subs in SUBCOMMANDS_WITH_SUBSUB.items()
    for ss in subs
])
def test_subsubcommand_help(runner, sub: str, subsub: str) -> None:
    result = runner([sub, subsub, "--help"])
    assert result.returncode == 0, (
        f"--help for '{sub} {subsub}' exited {result.returncode}:\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    combined = result.stdout + result.stderr
    assert len(combined) > 10
