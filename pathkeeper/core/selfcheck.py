"""pathkeeper self-diagnostic checks.

``run_selfcheck`` verifies that the pathkeeper installation is working correctly
end-to-end.  It is intended for users reporting bugs and for CI smoke tests.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_STATUS_PASS = "pass"  # nosec B105
_STATUS_FAIL = "fail"
_STATUS_WARN = "warn"


@dataclass
class SelfCheckResult:
    name: str
    status: str  # "pass" | "fail" | "warn"
    detail: str
    remediation: str = ""


@dataclass
class SelfCheckReport:
    checks: list[SelfCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.status == _STATUS_PASS for c in self.checks)

    @property
    def exit_code(self) -> int:
        return 0 if self.passed else 1


def run_selfcheck() -> SelfCheckReport:
    """Run all self-diagnostic checks and return the report."""
    report = SelfCheckReport()

    # 1. Backup directory exists and is writable
    from pathkeeper.config import backups_home

    backup_dir = backups_home()
    if not backup_dir.exists():
        report.checks.append(
            SelfCheckResult(
                "Backup directory",
                _STATUS_FAIL,
                f"{backup_dir} does not exist",
                "Run `pathkeeper backup` once to create it, or check ~/.pathkeeper/ permissions.",
            )
        )
    elif not _is_writable(backup_dir):
        report.checks.append(
            SelfCheckResult(
                "Backup directory",
                _STATUS_FAIL,
                f"{backup_dir} is not writable",
                "Check file system permissions on ~/.pathkeeper/backups/.",
            )
        )
    else:
        report.checks.append(
            SelfCheckResult(
                "Backup directory",
                _STATUS_PASS,
                str(backup_dir),
            )
        )

    # 2. Catalog present and parseable
    from pathkeeper.config import catalog_path

    cat_path = catalog_path()
    if not cat_path.exists():
        report.checks.append(
            SelfCheckResult(
                "Tool catalog",
                _STATUS_WARN,
                f"{cat_path} not found — will use bundled catalog",
                "Run `pathkeeper populate` once to copy the default catalog, or ignore this warning.",
            )
        )
    else:
        try:
            tomllib.loads(cat_path.read_text(encoding="utf-8"))
            report.checks.append(
                SelfCheckResult("Tool catalog", _STATUS_PASS, str(cat_path))
            )
        except Exception as exc:
            report.checks.append(
                SelfCheckResult(
                    "Tool catalog",
                    _STATUS_FAIL,
                    f"{cat_path} is not valid TOML: {exc}",
                    f"Delete {cat_path} and run `pathkeeper populate` to restore it.",
                )
            )

    # 3. Platform adapter can read PATH
    try:
        from pathkeeper.config import load_config
        from pathkeeper.core.path_reader import read_snapshot
        from pathkeeper.platform import get_platform_adapter

        config = load_config()
        adapter = get_platform_adapter(config)
        snapshot = read_snapshot(adapter)
        total = len(snapshot.system_path) + len(snapshot.user_path)
        report.checks.append(
            SelfCheckResult(
                "Platform adapter",
                _STATUS_PASS,
                f"read {total} PATH entries",
            )
        )
    except Exception as exc:
        report.checks.append(
            SelfCheckResult(
                "Platform adapter",
                _STATUS_FAIL,
                f"could not read PATH: {exc}",
                "Check platform adapter permissions (elevated shell may be needed on Windows).",
            )
        )

    # 4. Auto-backup is configured (schedule or shell startup hook)
    auto_configured = _check_auto_backup()
    if auto_configured is None:
        report.checks.append(
            SelfCheckResult(
                "Auto-backup",
                _STATUS_WARN,
                "no schedule or shell-startup hook detected",
                (
                    "Run `pathkeeper schedule install` to enable scheduled backups, "
                    "or `pathkeeper shell-startup` to add a hook to your shell rc file."
                ),
            )
        )
    else:
        report.checks.append(
            SelfCheckResult("Auto-backup", _STATUS_PASS, auto_configured)
        )

    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_writable(path: Path) -> bool:
    return os.access(str(path), os.W_OK)


def _check_auto_backup() -> str | None:
    """Return a description of the auto-backup mechanism, or None if absent."""
    import sys

    # Check shell startup hooks (bash, zsh, fish, PowerShell)
    shell_rc_candidates = [
        Path.home() / ".bashrc",
        Path.home() / ".bash_profile",
        Path.home() / ".zshrc",
        Path.home() / ".config" / "fish" / "config.fish",
    ]
    if sys.platform == "win32":
        userprofile = os.environ.get("USERPROFILE", str(Path.home()))
        shell_rc_candidates.append(
            Path(userprofile)
            / "Documents"
            / "WindowsPowerShell"
            / "Microsoft.PowerShell_profile.ps1"
        )
    marker = "pathkeeper backup"
    for rc in shell_rc_candidates:
        try:
            if rc.exists() and marker in rc.read_text(
                encoding="utf-8", errors="ignore"
            ):
                return f"shell-startup hook in {rc}"
        except OSError:
            continue

    # Check platform-level schedule
    try:
        from pathkeeper.core.schedule import schedule_status
        from pathkeeper.platform import normalized_os_name

        status = schedule_status(normalized_os_name())
        if status.enabled:
            return f"scheduled task: {status.detail}"
    except Exception as _exc:  # nosec B110
        pass

    return None
