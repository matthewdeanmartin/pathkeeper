# Configuration

`pathkeeper` stores user-controlled state in `~/.pathkeeper/`.

## Files

```text
~/.pathkeeper/
├── backups/
├── config.toml
└── known_tools.toml
```

## `config.toml`

The config file is created automatically with defaults the first time `pathkeeper` runs.

Current default shape:

```toml
[general]
max_backups = 100
max_auto_backups = 50
max_manual_backups = 50

[display]
color = true
unicode = true

[restore]
pre_backup = true

[populate]
extra_catalog = ""

[schedule]
enabled = false
interval = "startup"

[shell]
rc_file = ""
```

## Meaning of each section

### `[general]`

- `max_backups`: overall backup retention target
- `max_auto_backups`: how many `auto` backups to keep
- `max_manual_backups`: how many `manual` backups to keep

### `[display]`

These values are reserved for output preferences. The current CLI keeps output simple and text-based, but the settings are already part of the stored config shape.

### `[restore]`

- `pre_backup`: when true, `restore` creates a `pre-restore` backup unless `--no-pre-backup` is passed

### `[populate]`

- `extra_catalog`: optional path to a user catalog file merged with the built-in known-tools catalog

### `[schedule]`

- `enabled`: stored state for scheduling preferences
- `interval`: preferred interval string, such as `startup`

### `[shell]`

- `rc_file`: overrides shell rc auto-detection on Unix-like systems

## `known_tools.toml`

The bundled catalog is copied into `~/.pathkeeper/known_tools.toml` on first run so you can edit it locally.

The current default catalog includes patterns for Python, Node.js, Go, Rust, Ruby, Java, .NET, PHP, Dart, Deno, Git, Docker, kubectl, Terraform, VS Code, PostgreSQL, MySQL, MongoDB, SQLite, Homebrew, Snap, Flatpak, Composer, Maven, and Gradle.
