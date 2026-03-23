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
