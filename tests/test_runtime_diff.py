"""Tests for the runtime PATH diff feature."""

from __future__ import annotations

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig
from pathkeeper.core.runtime_diff import detect_runtime_entries
from pathkeeper.models import PathSnapshot, Scope

# ---------------------------------------------------------------------------
# Unit tests for detect_runtime_entries
# ---------------------------------------------------------------------------


def test_detect_runtime_entries_all_persisted(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/user/bin")
    snapshot = PathSnapshot(
        system_path=["/usr/bin"],
        user_path=["/home/user/bin"],
        system_path_raw="/usr/bin",
        user_path_raw="/home/user/bin",
    )
    entries = detect_runtime_entries(snapshot, "linux")
    assert all(e.persisted for e in entries)
    assert len(entries) == 2


def test_detect_runtime_entries_finds_runtime_only(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/user/bin:/tmp/injected")
    snapshot = PathSnapshot(
        system_path=["/usr/bin"],
        user_path=["/home/user/bin"],
        system_path_raw="/usr/bin",
        user_path_raw="/home/user/bin",
    )
    entries = detect_runtime_entries(snapshot, "linux")
    runtime = [e for e in entries if not e.persisted]
    assert len(runtime) == 1
    assert runtime[0].value == "/tmp/injected"


def test_detect_runtime_entries_system_scope(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/user/bin")
    snapshot = PathSnapshot(
        system_path=["/usr/bin"],
        user_path=["/home/user/bin"],
        system_path_raw="/usr/bin",
        user_path_raw="/home/user/bin",
    )
    entries = detect_runtime_entries(snapshot, "linux")
    sys_entries = [e for e in entries if e.scope == Scope.SYSTEM]
    assert len(sys_entries) == 1
    assert sys_entries[0].value == "/usr/bin"


def test_detect_runtime_entries_empty_path(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    snapshot = PathSnapshot(
        system_path=["/usr/bin"],
        user_path=["/home/user/bin"],
        system_path_raw="/usr/bin",
        user_path_raw="/home/user/bin",
    )
    entries = detect_runtime_entries(snapshot, "linux")
    assert entries == []


def test_detect_runtime_entries_windows_separator(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", r"C:\Windows\System32;C:\injected")
    snapshot = PathSnapshot(
        system_path=[r"C:\Windows\System32"],
        user_path=[],
        system_path_raw=r"C:\Windows\System32",
        user_path_raw="",
    )
    entries = detect_runtime_entries(snapshot, "windows")
    persisted = [e for e in entries if e.persisted]
    runtime = [e for e in entries if not e.persisted]
    assert len(persisted) == 1
    assert len(runtime) == 1
    assert runtime[0].value == r"C:\injected"


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


def test_runtime_entries_cli_all_persisted(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/user/bin")
    _stub_adapter(monkeypatch, ["/usr/bin"], ["/home/user/bin"])
    exit_code = cli.run(["runtime-entries"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "No runtime-only" in output or "All PATH entries match" in output


def test_runtime_entries_cli_finds_injected(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/user/bin:/tmp/injected")
    _stub_adapter(monkeypatch, ["/usr/bin"], ["/home/user/bin"])
    exit_code = cli.run(["runtime-entries"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "runtime" in output.lower()
    assert "/tmp/injected" in output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _stub_adapter(
    monkeypatch: MonkeyPatch,
    system: list[str],
    user: list[str],
) -> None:
    monkeypatch.setattr(
        cli, "get_platform_adapter", lambda _: _StubAdapter(system, user)
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
