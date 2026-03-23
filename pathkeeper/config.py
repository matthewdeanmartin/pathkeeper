from __future__ import annotations

import shutil
import tomllib
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

APP_DIR_NAME = ".pathkeeper"
BACKUP_DIR_NAME = "backups"
CATALOG_FILE_NAME = "known_tools.toml"
CONFIG_FILE_NAME = "config.toml"


@dataclass(frozen=True)
class GeneralConfig:
    max_backups: int = 100
    max_auto_backups: int = 50
    max_manual_backups: int = 50


@dataclass(frozen=True)
class DisplayConfig:
    color: bool = True
    unicode: bool = True


@dataclass(frozen=True)
class RestoreConfig:
    pre_backup: bool = True


@dataclass(frozen=True)
class PopulateConfig:
    extra_catalog: str = ""


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool = False
    interval: str = "startup"


@dataclass(frozen=True)
class ShellConfig:
    rc_file: str = ""


@dataclass(frozen=True)
class AppConfig:
    general: GeneralConfig = field(default_factory=GeneralConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    restore: RestoreConfig = field(default_factory=RestoreConfig)
    populate: PopulateConfig = field(default_factory=PopulateConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    shell: ShellConfig = field(default_factory=ShellConfig)


def app_home() -> Path:
    return Path.home() / APP_DIR_NAME


def backups_home() -> Path:
    return app_home() / BACKUP_DIR_NAME


def config_path() -> Path:
    return app_home() / CONFIG_FILE_NAME


def catalog_path() -> Path:
    return app_home() / CATALOG_FILE_NAME


def ensure_app_state() -> None:
    app_home().mkdir(parents=True, exist_ok=True)
    backups_home().mkdir(parents=True, exist_ok=True)
    if not config_path().exists():
        write_default_config(config_path())
    if not catalog_path().exists():
        source = resources.files("pathkeeper.catalog").joinpath(CATALOG_FILE_NAME)
        with (
            source.open("rb") as source_handle,
            catalog_path().open("wb") as target_handle,
        ):
            shutil.copyfileobj(source_handle, target_handle)


def write_default_config(path: Path) -> None:
    default = AppConfig()
    path.write_text(_render_config(default), encoding="utf-8")


def _render_bool(value: bool) -> str:
    return "true" if value else "false"


def _render_config(config: AppConfig) -> str:
    return "\n".join(
        [
            "[general]",
            f"max_backups = {config.general.max_backups}",
            f"max_auto_backups = {config.general.max_auto_backups}",
            f"max_manual_backups = {config.general.max_manual_backups}",
            "",
            "[display]",
            f"color = {_render_bool(config.display.color)}",
            f"unicode = {_render_bool(config.display.unicode)}",
            "",
            "[restore]",
            f"pre_backup = {_render_bool(config.restore.pre_backup)}",
            "",
            "[populate]",
            f'extra_catalog = "{config.populate.extra_catalog}"',
            "",
            "[schedule]",
            f"enabled = {_render_bool(config.schedule.enabled)}",
            f'interval = "{config.schedule.interval}"',
            "",
            "[shell]",
            f'rc_file = "{config.shell.rc_file}"',
            "",
        ]
    )


def load_config() -> AppConfig:
    ensure_app_state()
    raw = tomllib.loads(config_path().read_text(encoding="utf-8"))
    default = AppConfig()
    return AppConfig(
        general=GeneralConfig(**{**asdict(default.general), **raw.get("general", {})}),
        display=DisplayConfig(**{**asdict(default.display), **raw.get("display", {})}),
        restore=RestoreConfig(**{**asdict(default.restore), **raw.get("restore", {})}),
        populate=PopulateConfig(
            **{**asdict(default.populate), **raw.get("populate", {})}
        ),
        schedule=ScheduleConfig(
            **{**asdict(default.schedule), **raw.get("schedule", {})}
        ),
        shell=ShellConfig(**{**asdict(default.shell), **raw.get("shell", {})}),
    )
