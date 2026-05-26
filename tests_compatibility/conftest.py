"""
Compatibility test suite configuration.

The CLI under test is driven by the PK environment variable or the
--pk pytest option.  Examples:

    # Python (default)
    uv run pytest tests_compatibility/

    # Explicit Python module
    PK="python -m pathkeeper" uv run pytest tests_compatibility/

    # Go build
    PK=./bin/pathkeeper uv run pytest tests_compatibility/

    # Java jar
    PK="java -jar pathkeeper.jar" uv run pytest tests_compatibility/
"""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# pytest option
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--pk",
        default=None,
        help="CLI command to test, e.g. './bin/pathkeeper' or 'java -jar pk.jar'. "
        "Overrides the PK environment variable.",
    )


# ---------------------------------------------------------------------------
# Platform helpers (shared by fixtures and tests)
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    return platform.system() == "Windows" or os.environ.get("OS") == "Windows_NT"


def path_sep() -> str:
    return ";" if _is_windows() else ":"


def real_dirs() -> tuple[str, str, str, str]:
    """Four real directories that exist on every supported OS."""
    if _is_windows():
        return (
            r"C:\Windows",
            r"C:\Windows\system32",
            r"C:\Windows\System32\Wbem",
            r"C:\Windows\System32\WindowsPowerShell\v1.0",
        )
    return "/tmp", "/usr/bin", "/usr/local/bin", "/bin"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pk_cmd(request: pytest.FixtureRequest) -> list[str]:
    """Return the CLI command as a list of tokens."""
    raw = request.config.getoption("--pk") or os.environ.get("PK")
    if raw:
        return shlex.split(raw)
    # Default: run via the same interpreter that is running pytest
    return [sys.executable, "-m", "pathkeeper"]


@pytest.fixture(scope="session")
def sep() -> str:
    return path_sep()


@pytest.fixture(scope="session")
def dirs() -> tuple[str, str, str, str]:
    return real_dirs()


@pytest.fixture()
def pk_home(tmp_path: Path) -> Path:
    """Isolated PATHKEEPER_HOME for each test."""
    home = tmp_path / "pk_home"
    home.mkdir()
    return home


@pytest.fixture()
def pathx(dirs: tuple[str, str, str, str], sep: str) -> str:
    """A PATHX value made of real directories."""
    a, b, c, _ = dirs
    return sep.join([a, b, c])


@pytest.fixture()
def pathx_with_dupe(dirs: tuple[str, str, str, str], sep: str) -> str:
    """A PATHX value that intentionally contains a duplicate."""
    a, b, _c, _d = dirs
    return sep.join([a, b, a])


@pytest.fixture()
def runner(pk_cmd: list[str], pk_home: Path):
    """
    Returns a callable run(args, *, env_extra, input_text) -> CompletedProcess.
    Merges pk_home into env automatically.
    """

    def _run(
        args: list[str],
        *,
        env_extra: dict[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PATHKEEPER_HOME"] = str(pk_home)
        env["NO_COLOR"] = "1"  # suppress ANSI in output
        env["TERM"] = "dumb"
        env["PYTHONUTF8"] = "1"  # avoid cp1252 crashes on Windows
        if env_extra:
            env.update(env_extra)
        full_cmd = pk_cmd + args
        return subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            input=input_text,
            timeout=timeout,
        )

    return _run
