from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from _pytest.capture import CaptureFixture
from _pytest.monkeypatch import MonkeyPatch

import pathkeeper.core.schedule as _schedule_mod
from pathkeeper import cli
from pathkeeper.config import AppConfig
from pathkeeper.core.schedule import ScheduleStatus
from pathkeeper.errors import PermissionDeniedError
from pathkeeper.models import BackupRecord


class StubAdapter:
    def __init__(
        self,
        system: list[str],
        user: list[str],
        *,
        system_env: dict[str, str] | None = None,
        user_env: dict[str, str] | None = None,
    ) -> None:
        self._system = system
        self._user = user
        self._system_env = dict(system_env or {})
        self._user_env = dict(user_env or {})

    @staticmethod
    def _separator(entries: list[str]) -> str:
        if any("\\" in entry or entry.startswith("%") for entry in entries):
            return ";"
        return ":"

    def read_system_path(self) -> list[str]:
        return list(self._system)

    def read_user_path(self) -> list[str]:
        return list(self._user)

    def read_system_path_raw(self) -> str:
        return self._separator(self._system).join(self._system)

    def read_user_path_raw(self) -> str:
        return self._separator(self._user).join(self._user)

    def read_system_environment(self) -> dict[str, str]:
        return dict(self._system_env)

    def read_user_environment(self) -> dict[str, str]:
        return dict(self._user_env)

    def write_system_path(self, entries: list[str]) -> None:
        self._system = list(entries)

    def write_user_path(self, entries: list[str]) -> None:
        self._user = list(entries)

    def write_system_env_var(self, name: str, value: str) -> None:
        self._system_env[name] = value

    def write_user_env_var(self, name: str, value: str) -> None:
        self._user_env[name] = value

    def delete_system_env_var(self, name: str) -> None:
        self._system_env.pop(name, None)

    def delete_user_env_var(self, name: str) -> None:
        self._user_env.pop(name, None)


class GuardedSystemWriteAdapter(StubAdapter):
    def write_system_path(self, entries: list[str]) -> None:
        raise AssertionError("system PATH should not have been written")


class DenyingSystemWriteAdapter(StubAdapter):
    def write_system_path(self, entries: list[str]) -> None:
        raise PermissionDeniedError("Access denied writing the system PATH.")


class NonWritableSystemAdapter(StubAdapter):
    def ensure_system_writable(self) -> None:
        raise PermissionDeniedError("Access denied writing the system PATH.")


def _write_backup(path: Path, *, timestamp: str, tag: str, note: str = "") -> None:
    record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat(timestamp.replace("Z", "+00:00")),
        hostname="host",
        os_name="windows",
        tag=tag,
        note=note,
        system_path=["C:\\Windows\\System32"],
        user_path=["C:\\Users\\matth\\bin"],
        system_path_raw="C:\\Windows\\System32",
        user_path_raw="C:\\Users\\matth\\bin",
    )
    path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")


def test_doctor_json_output(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/missing", "/usr/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["doctor", "--json"])
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["summary"]["duplicates"] == 1
    assert payload["summary"]["invalid"] >= 1


def test_backup_command_writes_to_overridden_backup_home(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["backup"])
    assert exit_code == 0
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert "Created backup:" in capsys.readouterr().out


def test_backup_command_logs_info_when_requested(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.main(["--log-level", "info", "backup", "--quiet", "--force"])
    error_output = capsys.readouterr().err
    assert exit_code == 0
    assert "INFO: Running backup with tag=manual" in error_output


def test_backup_dry_run_reports_planned_backup(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["backup", "--dry-run"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run: would create backup at" in output
    assert len(list(tmp_path.glob("*.json"))) == 0


def test_backup_command_skips_duplicate_content_without_force(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    assert cli.main(["backup", "--quiet"]) == 0
    capsys.readouterr()
    exit_code = cli.main(["backup", "--quiet"])
    error_output = capsys.readouterr().err
    assert exit_code == 0
    assert (
        "WARNING: Skipping backup because the current PATH matches the latest saved backup."
        in error_output
    )


def test_backup_dry_run_reports_duplicate_skip(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    assert cli.run(["backup"]) == 0
    capsys.readouterr()
    exit_code = cli.run(["backup", "--dry-run"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run: backup would be skipped" in output


def test_dedupe_all_skips_unchanged_system_scope(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    user_bin = tmp_path / "user-bin"
    user_bin.mkdir()
    adapter = GuardedSystemWriteAdapter(
        system=["C:\\Windows\\System32"], user=[str(user_bin), str(user_bin)]
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    exit_code = cli.run(["dedupe", "--scope", "all", "--force", "--no-remove-invalid"])
    assert exit_code == 0
    assert adapter.read_system_path() == ["C:\\Windows\\System32"]
    assert adapter.read_user_path() == [str(user_bin)]
    assert "Dedupe complete." in capsys.readouterr().out


def test_dedupe_all_reports_permission_error_for_changed_system_scope(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    system_bin = tmp_path / "system-bin"
    system_bin.mkdir()
    adapter = DenyingSystemWriteAdapter(
        system=[str(system_bin), str(system_bin)], user=[]
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    exit_code = cli.main(["dedupe", "--scope", "all", "--force"])
    assert exit_code == PermissionDeniedError.exit_code
    assert "Access denied writing the system PATH." in capsys.readouterr().err


def test_dedupe_all_preflights_system_scope_before_backup_or_prompt(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    system_bin = tmp_path / "system-bin"
    system_bin.mkdir()
    adapter = NonWritableSystemAdapter(
        system=[str(system_bin), str(system_bin)], user=[]
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt="": (_ for _ in ()).throw(
            AssertionError("input should not be called")
        ),
    )
    exit_code = cli.main(["dedupe", "--scope", "all"])
    assert exit_code == PermissionDeniedError.exit_code
    assert not (tmp_path / "backups").exists()
    assert "Access denied writing the system PATH." in capsys.readouterr().err


def test_backups_list_prints_available_backups(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T11-00-00_pre-dedupe.json",
        timestamp="2025-03-02T11:00:00Z",
        tag="pre-dedupe",
        note="Before dedupe",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["backups", "list"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Most recent backups" in output
    assert "│ # │ Backup" in output
    assert "│ 1 │ 2025-03-02T11-00-00_pre-dedupe.json" in output
    assert "2025-03-02T11-00-00_pre-dedupe.json" in output
    assert "2025-03-02 11:00Z" in output
    assert "Hash" in output
    assert "Before dedupe" in output


def test_backups_show_defaults_to_latest_backup(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T11-00-00_pre-dedupe.json",
        timestamp="2025-03-02T11:00:00Z",
        tag="pre-dedupe",
        note="Before dedupe",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    exit_code = cli.run(["backups", "show"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Most recent backups:" in output
    assert "│ # │ Backup" in output
    assert "2025-03-02 11:00Z" in output
    assert "Backup: 2025-03-02T11-00-00_pre-dedupe.json" in output
    assert "Timestamp: 2025-03-02 11:00Z" in output
    assert "Content hash:" in output
    assert "Tag: pre-dedupe" in output
    assert "User PATH:" in output


def test_backups_show_accepts_recent_index(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    _write_backup(
        tmp_path / "2025-03-01T10-00-00_manual.json",
        timestamp="2025-03-01T10:00:00Z",
        tag="manual",
    )
    _write_backup(
        tmp_path / "2025-03-02T11-00-00_pre-dedupe.json",
        timestamp="2025-03-02T11:00:00Z",
        tag="pre-dedupe",
    )
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    exit_code = cli.run(["backups", "show", "2"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Backup: 2025-03-01T10-00-00_manual.json" in output


def test_interactive_menu_includes_backup_browser(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    monkeypatch.setattr(cli, "list_backups", lambda _path: [])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(
        cli,
        "get_platform_adapter",
        lambda _config: StubAdapter(system=[str(good_dir)], user=["/missing"]),
    )
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: Path("C:\\backups"))
    monkeypatch.setattr("builtins.input", lambda _prompt="": "q")
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "0 backup(s) in" in output
    assert "entries=2" in output
    assert "valid=1" in output
    assert "invalid=1" in output
    assert "List backups" in output
    assert "Show backup" in output
    assert "Edit" in output
    assert "Repair truncated" in output
    assert "Split long" in output
    assert "Schedule status" in output


def test_interactive_edit_session_can_stage_and_write_changes(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)
    responses = iter(["9", "", 'add "/opt/tools/bin"', "preview", "write", "y", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Editing USER PATH (1 entries):" in output
    assert "Commands:" in output
    assert "Added staged entry." in output
    assert "Added:" in output
    assert "Edit complete." in output
    assert "Edit finished with exit code 0." not in output
    assert adapter.read_user_path() == ["/home/test/bin", "/opt/tools/bin"]


def test_edit_dry_run_shows_diff_without_writing(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(system=["/usr/bin"], user=["/home/test/bin"])
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "linux")
    exit_code = cli.run(["edit", "--add", "/opt/tools/bin", "--dry-run"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Added:" in output
    assert "Dry run: edit changes were not written." in output
    assert adapter.read_user_path() == ["/home/test/bin"]


def test_interactive_cancel_returns_to_menu(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    user_bin = tmp_path / "user-bin"
    user_bin.mkdir()
    adapter = StubAdapter(
        system=["C:\\Windows\\System32"], user=[str(user_bin), str(user_bin)]
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    responses = iter(["7", "n", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "User cancelled." in output
    # Menu re-displays after cancellation; verify menu entries appear at least twice
    assert output.count("Dedupe") >= 2


def test_interactive_dedupe_offers_user_scope_fallback_on_windows_permission_error(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    user_bin = tmp_path / "user-bin"
    user_bin.mkdir()
    system_bin = tmp_path / "system-bin"
    system_bin.mkdir()
    adapter = NonWritableSystemAdapter(
        system=[str(system_bin), str(system_bin)],
        user=[str(user_bin), str(user_bin)],
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    responses = iter(["7", "", "y", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "System PATH changes need an elevated shell" in output
    assert "Dedupe complete." in output
    assert adapter.read_system_path() == [str(system_bin), str(system_bin)]
    assert adapter.read_user_path() == [str(user_bin)]


def test_repair_truncated_applies_single_backup_candidate(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    full_dir = (
        tmp_path
        / "Users"
        / "matth"
        / "AppData"
        / "Local"
        / "Programs"
        / "Python"
        / "Python314"
        / "Scripts"
    )
    full_dir.mkdir(parents=True)
    adapter = StubAdapter(
        system=[],
        user=["Users\\matth\\AppData\\Local\\Programs\\Python\\Python314\\Scripts"],
    )
    backup_record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat("2025-03-02T11:00:00+00:00"),
        hostname="host",
        os_name="windows",
        tag="manual",
        note="",
        system_path=[],
        user_path=[str(full_dir)],
        system_path_raw="",
        user_path_raw=str(full_dir),
        source_file=tmp_path / "2025-03-02T11-00-00_manual.json",
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path / "backups")
    monkeypatch.setattr(cli, "list_backups", lambda _path: [backup_record])
    responses = iter(["y", "y"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run(["repair-truncated", "--scope", "user"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Suggested repair:" in output
    assert "Truncated PATH repair complete." in output
    assert adapter.read_user_path() == [str(full_dir)]


def test_split_long_dry_run_reports_plan(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(
        system=[],
        user=[
            r"C:\Tools\Alpha\bin",
            r"C:\Tools\Beta\bin",
            r"C:\Tools\Gamma\bin",
            r"C:\Tools\Delta\bin",
        ],
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")

    exit_code = cli.run(
        [
            "split-long",
            "--dry-run",
            "--max-length",
            "40",
            "--chunk-length",
            "32",
            "--var-prefix",
            "DEV_PATHS",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Helper variable values:" in output
    assert "%DEV_PATHS_1%" in output
    assert "[dry-run] No changes written." in output
    assert adapter.read_user_path()[-1] == r"C:\Tools\Delta\bin"
    assert adapter.read_user_environment() == {}


def test_split_long_writes_helper_vars_and_updates_path(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    adapter = StubAdapter(
        system=[],
        user=[
            r"C:\Tools\Alpha\bin",
            r"C:\Tools\Beta\bin",
            r"C:\Tools\Gamma\bin",
            r"C:\Tools\Delta\bin",
        ],
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)

    exit_code = cli.run(
        [
            "split-long",
            "--force",
            "--max-length",
            "40",
            "--chunk-length",
            "32",
            "--var-prefix",
            "DEV_PATHS",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Split-long complete." in output
    assert all(entry.startswith("%DEV_PATHS_") for entry in adapter.read_user_path())
    assert set(adapter.read_user_environment()) == {"DEV_PATHS_1"}
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_restore_rehydrates_helper_environment_variables(
    monkeypatch: MonkeyPatch, tmp_path: Path, capsys: CaptureFixture[str]
) -> None:
    backup_path = tmp_path / "2025-03-05T10-00-00_manual.json"
    record = BackupRecord(
        version=1,
        timestamp=datetime.fromisoformat("2025-03-05T10:00:00+00:00"),
        hostname="host",
        os_name="windows",
        tag="manual",
        note="",
        system_path=[],
        user_path=["%PK_USER_PATHS_1%"],
        system_path_raw="",
        user_path_raw="%PK_USER_PATHS_1%",
        user_env_vars={"PK_USER_PATHS_1": r"C:\Tools\Alpha\bin;C:\Tools\Beta\bin"},
        source_file=backup_path,
    )
    backup_path.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
    adapter = StubAdapter(
        system=[], user=[r"C:\Temp\bin"], user_env={"OLD_PATHS_1": "x"}
    )
    monkeypatch.setattr(cli, "load_config", lambda: AppConfig())
    monkeypatch.setattr(cli, "get_platform_adapter", lambda _config: adapter)
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(cli, "backups_home", lambda: tmp_path)

    exit_code = cli.run(
        ["restore", str(backup_path), "--scope", "user", "--force", "--no-pre-backup"]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Restore complete." in output
    assert adapter.read_user_path() == ["%PK_USER_PATHS_1%"]
    assert adapter.read_user_environment()["PK_USER_PATHS_1"] == (
        r"C:\Tools\Alpha\bin;C:\Tools\Beta\bin"
    )


def test_schedule_status_hides_low_level_disabled_detail(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(
        _schedule_mod,
        "schedule_status",
        lambda _os_name: ScheduleStatus(
            False, "ERROR: The system cannot find the file specified."
        ),
    )
    exit_code = cli.run(["schedule", "status"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Schedule is disabled." in output
    assert "pathkeeper schedule install" in output
    assert "cannot find the file" not in output.lower()


def test_schedule_install_dry_run_reports_plan(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    exit_code = cli.run(["schedule", "install", "--trigger", "logon", "--dry-run"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert (
        "Dry run: would install scheduled backups for os=windows interval=startup trigger=logon."
        in output
    )


def test_schedule_remove_dry_run_reports_plan(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    exit_code = cli.run(["schedule", "remove", "--dry-run"])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Dry run: would remove scheduled backups for os=windows." in output


def test_interactive_schedule_status_offers_install_when_disabled(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(
        _schedule_mod,
        "schedule_status",
        lambda _os_name: ScheduleStatus(False, "missing"),
    )
    monkeypatch.setattr(
        _schedule_mod,
        "install_schedule",
        lambda _os_name, _interval, *, trigger="startup": "Installed Windows scheduled task.",
    )
    responses = iter(["12", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Scheduled backups are not set up yet." in output
    assert "Installed Windows scheduled task." in output


def test_interactive_schedule_status_falls_back_to_logon_on_windows_permission_error(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(
        _schedule_mod,
        "schedule_status",
        lambda _os_name: ScheduleStatus(False, "missing"),
    )

    def fake_install(_os_name: str, _interval: str, *, trigger: str = "startup") -> str:
        if trigger == "startup":
            raise PermissionDeniedError("Access is denied.")
        return "Installed Windows scheduled task for user logon."

    monkeypatch.setattr(_schedule_mod, "install_schedule", fake_install)
    responses = iter(["12", "", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Installing a startup task on Windows needs an elevated shell." in output
    assert "Installed Windows scheduled task for user logon." in output


def test_interactive_schedule_status_explains_when_logon_fallback_is_also_denied(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")
    monkeypatch.setattr(
        _schedule_mod,
        "schedule_status",
        lambda _os_name: ScheduleStatus(False, "missing"),
    )

    def fake_install(_os_name: str, _interval: str, *, trigger: str = "startup") -> str:
        raise PermissionDeniedError("Access is denied.")

    monkeypatch.setattr(_schedule_mod, "install_schedule", fake_install)
    responses = iter(["12", "", "", "q"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(responses))
    exit_code = cli.run([])
    output = capsys.readouterr().out
    error_output = capsys.readouterr().err
    assert exit_code == 0
    assert "Installing a startup task on Windows needs an elevated shell." in output
    assert "Windows denied creation of the per-user logon task too." in output
    assert "Run pathkeeper from an elevated shell" in output
    assert error_output == ""


def test_schedule_install_permission_error_is_cleaned(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "normalized_os_name", lambda: "windows")

    def fake_install(_os_name: str, _interval: str, *, trigger: str = "startup") -> str:
        raise PermissionDeniedError("Access is denied.")

    monkeypatch.setattr(_schedule_mod, "install_schedule", fake_install)
    exit_code = cli.main(["schedule", "install"])
    error_output = capsys.readouterr().err
    assert exit_code == PermissionDeniedError.exit_code
    assert "ERROR: Access is denied." in error_output
