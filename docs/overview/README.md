# Overview

`pathkeeper` helps you recover from one of the most frustrating machine setup problems: a broken `PATH`.

It creates local backups, diagnoses common problems, and gives you a safer way to restore or clean up PATH after an installer, shell tweak, or manual edit goes wrong.

## Current feature set

The current implementation provides:

- `backup` to snapshot current system and user PATH values
- `inspect` to list entries and their health
- `doctor` to summarize problems and suggest next steps
- `restore` to restore a previous backup by filename or timestamp prefix
- `dedupe` to remove duplicates and optionally invalid entries
- `populate` to discover common tool directories from a catalog
- `edit` for direct non-interactive PATH edits
- `schedule` to install, remove, or inspect automated backups
- an interactive menu when you run `pathkeeper` with no arguments

## Safety model

The tool is built around a few simple rules:

- backups are stored locally in `~/.pathkeeper/backups/`
- mutating commands create pre-operation backups where supported
- restores and cleanup commands show a diff or preview before writing
- on Unix, `pathkeeper` only rewrites the PATH block it owns in shell rc files
- on Windows, writes use `REG_EXPAND_SZ` and broadcast environment changes

## Platform model

`pathkeeper` supports three platform families:

- Windows: user and system PATH come from the registry
- macOS: user PATH is managed in a shell rc file, system PATH is managed through `/etc/paths`
- Linux: user PATH is managed in a shell rc file, system PATH is managed through `/etc/environment`

## Where data lives

```text
~/.pathkeeper/
├── backups/
├── config.toml
└── known_tools.toml
```

This directory is created automatically on first run.
