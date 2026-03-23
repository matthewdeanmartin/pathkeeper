"""Tests for the first-run onboarding wizard."""
from __future__ import annotations

from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

from pathkeeper import cli
from pathkeeper.config import AppConfig


class StubAdapter:
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


def _patch_wizard_env(monkeypatch: MonkeyPatch, tmp_path: Path) -> Path:
    """Patch everything needed for the wizard to run in isolation."""
    app_dir = tmp_path / ".pathkeeper"
    # Do NOT create app_dir — wizard should detect its absence and create it

    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: app_dir / "backups")

    from pathkeeper import config as _config_mod
    monkeypatch.setattr(_config_mod, "app_home", lambda: app_dir)

    from pathkeeper.cli import _config_mod as _cli_config  # noqa: F401 – may not exist
    # Patch the imported name in cli's own namespace too (used in run() and wizard)
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr("pathkeeper.config.app_home", lambda: app_dir)
    return app_dir


def test_wizard_triggers_when_app_home_absent(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    assert not app_dir.exists()

    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: app_dir / "backups")
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    # Wizard asks: create backup? and install hook?  say no to both to keep test simple
    responses = iter(["n", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Welcome to pathkeeper" in output
    assert "first time" in output.lower() or "new" in output.lower()


def test_wizard_does_not_trigger_when_app_home_exists(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    app_dir.mkdir()

    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: app_dir / "backups")
    monkeypatch.setattr(cli, "list_backups", lambda _path: [])
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")

    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    # Should see interactive menu, not the wizard
    assert "Welcome to pathkeeper" not in output
    assert "Inspect" in output or "Doctor" in output  # menu entries


def test_wizard_shows_path_health_summary(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: app_dir / "backups")
    responses = iter(["n", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    # Should report the health of the current PATH
    assert "entries" in output.lower() or "valid" in output.lower()


def test_wizard_creates_backup_when_user_accepts(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    backup_dir = app_dir / "backups"
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: backup_dir)
    # Accept backup, decline shell hook
    responses = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    exit_code = cli.run([])
    capsys.readouterr()
    assert exit_code == 0
    # A backup file should have been created
    assert backup_dir.exists()
    assert len(list(backup_dir.glob("*.json"))) == 1


def test_wizard_skips_backup_when_user_declines(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    backup_dir = app_dir / "backups"
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: backup_dir)
    # Decline both prompts
    responses = iter(["n", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    exit_code = cli.run([])
    capsys.readouterr()
    assert exit_code == 0
    assert not backup_dir.exists() or len(list(backup_dir.glob("*.json"))) == 0


def test_wizard_setup_complete_message(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    app_dir = tmp_path / ".pathkeeper"
    import pathkeeper.config as _pkconfig
    monkeypatch.setattr(_pkconfig, "app_home", lambda: app_dir)
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli, "get_platform_adapter",
        lambda _config: StubAdapter(system=["/usr/bin"], user=["/home/user/bin"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: app_dir / "backups")
    responses = iter(["n", "n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))

    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Setup complete" in output or "complete" in output.lower()
