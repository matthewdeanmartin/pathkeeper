# pathkeeper

`pathkeeper` is a typed Python 3.14 CLI for backing up, inspecting, diagnosing, restoring, deduplicating, populating, and editing the PATH environment variable.

It is designed to help when a bad installer, shell tweak, or system tool mangles PATH and you need a reliable way to recover.

## What it does

- Creates versioned PATH backups in `~/.pathkeeper/backups/`
- Diagnoses duplicates, invalid entries, empty entries, files-instead-of-directories, and Windows length limits
- Restores system, user, or both PATH scopes from a saved snapshot
- Creates safety backups before mutating operations
- Deduplicates PATH entries and can remove invalid directories
- Discovers common developer tool directories that are missing from PATH
- Supports direct subcommands and a simple interactive menu
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
uv run pathkeeper inspect
uv run pathkeeper doctor
uv run pathkeeper backup --note "before installing toolchain"
uv run pathkeeper restore 2025-03-05T14-30-00 --dry-run
uv run pathkeeper dedupe --dry-run
uv run pathkeeper populate --dry-run
uv run pathkeeper edit --add "/usr/local/newbin" --force
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
- On Unix, `pathkeeper` only rewrites PATH content inside its managed marker block in user rc files.
- On Windows, registry writes use `REG_EXPAND_SZ` and broadcast an environment change notification.
