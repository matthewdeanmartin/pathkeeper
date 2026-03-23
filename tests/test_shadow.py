"""Tests for the shadow detection feature."""

from __future__ import annotations

import json
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.core.shadow import find_shadows
from pathkeeper.models import Scope

# ---------------------------------------------------------------------------
# Unit tests for find_shadows
# ---------------------------------------------------------------------------


def test_find_shadows_returns_empty_when_no_dirs() -> None:
    groups = find_shadows(
        system_entries=[], user_entries=[], os_name="linux", scope=Scope.ALL
    )
    assert groups == []


def test_find_shadows_detects_shadowed_executable(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)
    (dir_b / "git").write_text("")
    (dir_b / "git").chmod(0o755)

    groups = find_shadows(
        system_entries=[str(dir_a)],
        user_entries=[str(dir_b)],
        os_name="linux",
        scope=Scope.ALL,
    )
    assert len(groups) == 1
    assert groups[0].name == "git"
    assert groups[0].winner.directory == str(dir_a)
    assert groups[0].winner.scope == Scope.SYSTEM
    assert groups[0].shadowed[0].directory == str(dir_b)


def test_find_shadows_no_shadow_when_unique_executables(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)
    (dir_b / "curl").write_text("")
    (dir_b / "curl").chmod(0o755)

    groups = find_shadows(
        system_entries=[str(dir_a)],
        user_entries=[str(dir_b)],
        os_name="linux",
        scope=Scope.ALL,
    )
    assert groups == []


def test_find_shadows_skips_duplicate_directories(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)

    # Same directory listed twice — should not count as a shadow
    groups = find_shadows(
        system_entries=[str(dir_a), str(dir_a)],
        user_entries=[],
        os_name="linux",
        scope=Scope.ALL,
    )
    assert groups == []


def test_find_shadows_scope_system_only(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)
    (dir_b / "git").write_text("")
    (dir_b / "git").chmod(0o755)

    # user dir should be ignored when scope=SYSTEM
    groups = find_shadows(
        system_entries=[str(dir_a)],
        user_entries=[str(dir_b)],
        os_name="linux",
        scope=Scope.SYSTEM,
    )
    assert groups == []


def test_find_shadows_sorted_by_name(tmp_path: Path) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    for name in ["zip", "awk"]:
        (dir_a / name).write_text("")
        (dir_a / name).chmod(0o755)
        (dir_b / name).write_text("")
        (dir_b / name).chmod(0o755)

    groups = find_shadows(
        system_entries=[str(dir_a), str(dir_b)],
        user_entries=[],
        os_name="linux",
        scope=Scope.ALL,
    )
    names = [g.name for g in groups]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_shadow_cli_no_shadows(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "unique_tool").write_text("")
    (dir_a / "unique_tool").chmod(0o755)

    _stub_adapter(monkeypatch, [str(dir_a)], [])
    exit_code = cli.run(["shadow"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No shadowed executables found" in output


def test_shadow_cli_shows_shadows(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)
    (dir_b / "git").write_text("")
    (dir_b / "git").chmod(0o755)

    _stub_adapter(monkeypatch, [str(dir_a)], [str(dir_b)])
    exit_code = cli.run(["shadow"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "git" in output
    assert "winner" in output
    assert "shadow" in output


def test_shadow_cli_json(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str], tmp_path: Path
) -> None:
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "git").write_text("")
    (dir_a / "git").chmod(0o755)
    (dir_b / "git").write_text("")
    (dir_b / "git").chmod(0o755)

    _stub_adapter(monkeypatch, [str(dir_a)], [str(dir_b)])
    exit_code = cli.run(["shadow", "--json"])
    output = capsys.readouterr().out
    assert exit_code == 0
    data = json.loads(output)
    assert len(data) == 1
    assert data[0]["name"] == "git"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_adapter(
    monkeypatch: MonkeyPatch,
    system: list[str],
    user: list[str],
) -> None:
    from pathkeeper.config import AppConfig

    monkeypatch.setattr(
        cli, "get_platform_adapter", lambda _: _StubAdapter(system, user)
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())


class _StubAdapter:
    def __init__(self, system: list[str], user: list[str]) -> None:
        self._system = system
        self._user = user

    def read_system_path(self) -> list[str]:
        return list(self._system)

    def read_user_path(self) -> list[str]:
        return list(self._user)

    def read_system_path_raw(self) -> str:
        return ":".join(self._system)

    def read_user_path_raw(self) -> str:
        return ":".join(self._user)
