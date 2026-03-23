# pathkeeper

`pathkeeper` designed to help when a bad installer, shell tweak, or system tool mangles PATH and you need a reliable way
to recover.

## Installation

`pipx install pathkeeper` or your other favorite global installatin method.

## Usage

Run `pathkeeper` and follow the startup. Or run `pathkeeper` again and follow the interactive commands. It also has a 
full bash CLI. Or run `pathkeeper gui` for tkinter GUI.

## What it does

`pathkeeper` is a typed Python CLI for backing up, inspecting, diagnosing, restoring, deduplicating, repairing truncated
entries, populating, and editing the PATH environment variable.

- Creates versioned PATH backups in `~/.pathkeeper/backups/`
- Diagnoses duplicates, invalid entries, empty entries, files-instead-of-directories, and Windows length limits
- Restores system, user, or both PATH scopes from a saved snapshot
- Creates safety backups before mutating operations
- Deduplicates PATH entries and can remove invalid directories
- Repairs likely truncated PATH entries by suggesting full matching directories from backup history or disk
- Discovers common developer tool directories that are missing from PATH
- Prefers the newest discovered version for versioned tool families such as Python and Node.js
- Supports direct subcommands and a simple interactive menu
- Interactive menu entries include short descriptions, and `Edit` opens a staged PATH editor instead of a read-only
  listing
- Includes schedule install/remove/status commands for automated backups

## Project layout

```text
pathkeeper/
├── pathkeeper/
├── tests/
├── pyproject.toml
├── Makefile
└── spec/
```

## Requirements

- Python 3.14
- `uv`
- `make` for the provided shortcuts

## Setup

```bash
make sync
```

Or directly:

```bash
uv sync --python 3.14
```

## Common commands

```bash
uv run pathkeeper --log-level info doctor
uv run pathkeeper inspect
uv run pathkeeper doctor
uv run pathkeeper backup --note "before installing toolchain"
uv run pathkeeper backup --force
uv run pathkeeper backup --dry-run
uv run pathkeeper backups list
uv run pathkeeper backups show
uv run pathkeeper backups show 2
uv run pathkeeper restore 2025-03-05T14-30-00 --dry-run
uv run pathkeeper dedupe --dry-run
uv run pathkeeper repair-truncated --scope user
uv run pathkeeper populate --dry-run
uv run pathkeeper edit --add "/usr/local/newbin" --dry-run
uv run pathkeeper edit --add "/usr/local/newbin" --force
uv run pathkeeper schedule install --dry-run
uv run pathkeeper schedule status
```

Run without arguments for the interactive menu:

```bash
uv run pathkeeper
```

## Quality checks

```bash
make test
make typecheck
make check
```

Or directly:

```bash
uv run pytest
uv run mypy pathkeeper tests
```

## Notes

- Backups preserve raw PATH strings so restore can round-trip values safely.
- Use `--log-level {info,warn,warning,error}` to control log verbosity.
- `pathkeeper backup` skips creating a new backup when the latest saved snapshot has identical PATH content unless you
  pass `--force`.
- Use `pathkeeper backups list` to see the most recent backups with a content hash, and
  `pathkeeper backups show [identifier-or-index]` to inspect one before restoring it.
- In the interactive menu, `Schedule status` offers to install automatic backups when scheduling is not set up yet.
- On Windows, if startup-task installation needs elevation, the interactive schedule flow offers a per-user logon task
  fallback.
- If Windows denies both the startup task and the logon-task fallback, the interactive schedule flow now explains the
  next step instead of exiting with a raw permission error.
- In the interactive menu, `Dedupe` now offers a user-scope fallback when system PATH changes need elevation on Windows.
- `backups list` now renders recent backups in a table that includes indices and content hashes.
- Backup tables use a compact UTC timestamp format with minute precision.
- Starting the interactive menu now shows the backup location plus a one-line inspect summary.
- If you cancel an interactive operation, pathkeeper returns to the menu instead of exiting.
- `repair-truncated` can propose repairs from backup history or disk matches and lets you choose among multiple
  candidates before writing.
- `backup`, `restore`, `dedupe`, `populate`, `repair-truncated`, `edit`, and scheduler writes all support dry-run
  preview flows.
- On Unix, `pathkeeper` only rewrites PATH content inside its managed marker block in user rc files.
- On Windows, registry writes use `REG_EXPAND_SZ` and broadcast an environment change notification.
