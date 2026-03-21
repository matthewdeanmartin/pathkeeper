# pathkeeper — Cross-Platform PATH Backup, Restore & Repair Tool

## Overview

`pathkeeper` is a cross-platform CLI tool for backing up, restoring, inspecting, deduplicating, editing, and populating the system PATH environment variable. It is written in Python (3.10+) and supports Windows, macOS, and Linux.

The primary interface is an **interactive CLI** (menu-driven TUI), with all commands also available as direct subcommands for scripting and automation.

### Prior Art

- [WindowsPathFix](https://github.com/clarboncy/WindowsPathFix) — PowerShell-only, Windows-only. Backs up PATH before repair, auto-discovers tool directories, removes duplicates/invalids. No versioned history, no restore workflow, no cross-platform support.
- [PyWinPath](https://github.com/czamb/pywinpath) — Python CLI for editing Windows PATH via registry. No backup/restore.
- [Path Backup & Restore](https://fumblydiddle.com/products/pathbackup/) — Windows GUI, exports to `.reg`/`.json`/`.yaml`. Manual only, no scheduling or versioning.
- [Environment.ahk](https://www.autohotkey.com/boards/viewtopic.php?t=30977) — AutoHotkey, Windows-only. Has backup/sort/dedupe functions but no version history.
- PowerToys Environment Variables — Profile-based, creates backup on profile apply. Not a general backup tool.

`pathkeeper` fills the gap: a single Python tool that works on all three OSes, maintains a versioned backup history, and provides an interactive workflow for inspection and repair.

---

## Concepts

### PATH Scopes

| OS | System PATH | User PATH |
| --- | --- | --- |
| **Windows** | Registry: `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment` → `Path` (type `REG_EXPAND_SZ`) | Registry: `HKCU\Environment` → `Path` (type `REG_EXPAND_SZ`) |
| **macOS** | `/etc/paths` + files in `/etc/paths.d/` | `~/.zprofile`, `~/.bash_profile`, `~/.config/fish/config.fish` (shell-dependent) |
| **Linux** | `/etc/environment`, files in `/etc/profile.d/` | `~/.bashrc`, `~/.zshrc`, `~/.profile`, `~/.config/fish/config.fish` (shell-dependent) |

On macOS/Linux, `pathkeeper` reads the **effective PATH** from the current environment (`$PATH`) for inspection/backup, but when restoring or editing it targets the appropriate **persistent source files** depending on the active shell. The user may override which file to target via config.

On Windows, `pathkeeper` reads and writes the registry directly using Python's `winreg` module. System PATH requires elevation (admin). User PATH does not.

### Backup Store

All backups live in a local directory:

```
~/.pathkeeper/
├── config.toml              # User configuration
├── backups/
│   ├── 2025-03-05T14-30-00_auto.json
│   ├── 2025-03-05T15-00-00_pre-restore.json
│   ├── 2025-03-06T09-12-33_manual.json
│   └── ...
└── known_tools.toml         # Editable catalog of common tool paths per OS
```

Each backup is a JSON file:

```json
{
  "version": 1,
  "timestamp": "2025-03-05T14:30:00Z",
  "hostname": "DESKTOP-ABC",
  "os": "windows",
  "tag": "auto",
  "note": "",
  "system_path": ["C:\\Windows\\system32", "C:\\Windows", "..."],
  "user_path": ["C:\\Users\\matt\\AppData\\Local\\Programs\\...", "..."],
  "system_path_raw": "C:\\Windows\\system32;C:\\Windows;...",
  "user_path_raw": "..."
}
```

The `_raw` fields preserve the original string exactly (including unexpanded `%VARS%` on Windows or `$HOME` references on Unix), ensuring lossless round-trip restore.

### Tags

Every backup has a `tag` indicating how it was created:

- `manual` — user explicitly ran `pathkeeper backup`
- `auto` — created by a scheduled task / cron job / launchd agent
- `pre-restore` — automatically created before any restore operation
- `pre-edit` — automatically created before any edit operation
- `pre-dedupe` — automatically created before deduplication
- `pre-populate` — automatically created before populating with common paths

---

## Commands

### `pathkeeper` (no args) — Interactive Mode

Launches a menu-driven interactive session. This is the **primary** interface.

```
╭─────────────────────────────────╮
│        pathkeeper v0.1.0        │
│   PATH Backup & Repair Tool    │
╰─────────────────────────────────╯

Current PATH: 14 entries (3 invalid, 2 duplicates)

  [1] Inspect     — View and analyze current PATH
  [2] Backup      — Snapshot current PATH
  [3] Restore     — Restore from a previous backup
  [4] Dedupe      — Remove duplicate entries
  [5] Populate    — Add common tool directories
  [6] Edit        — Interactively add/remove/reorder entries
  [7] Settings    — Configure pathkeeper
  [q] Quit

>
```

Navigation: number keys to select, `q` or Ctrl-C to exit. Submenus use the same pattern. Confirmations are required before any write operation.

### `pathkeeper inspect`

Displays the current PATH with diagnostics.

**Output includes:**

1. **Entry listing** — each entry numbered, with status indicators:
   - `✓` exists and is a directory
   - `✗` does not exist
   - `⚠` exists but is a file, not a directory
   - `D` duplicate of an earlier entry
   - `→` contains unexpanded variables (Windows `%VAR%`, Unix `$VAR`)
2. **Summary stats** — total entries, valid, invalid, duplicates, empty entries
3. **Scope breakdown** — which entries come from system vs. user PATH (Windows only; on Unix shows effective merged PATH)
4. **Length warning** — on Windows, warn if total PATH string exceeds 2047 characters (the `setx` limit) or 32767 characters (the absolute registry limit)

**Flags:**

- `--scope {system,user,all}` — which PATH to inspect (default: `all`)
- `--json` — output as JSON for scripting
- `--only-invalid` — show only entries that don't exist on disk
- `--only-dupes` — show only duplicate entries

**Interactive mode additions:** after displaying, offer sub-actions:
- "Delete invalid entries?" (→ runs dedupe with invalid filter)
- "Delete duplicates?" (→ runs dedupe)

### `pathkeeper backup`

Creates a timestamped backup of the current PATH.

```
pathkeeper backup [--note "before installing conda"] [--tag manual]
```

**Behavior:**

1. Read system and user PATH from their canonical sources (registry on Windows, env + source files on Unix).
2. Write JSON backup file to `~/.pathkeeper/backups/`.
3. Print confirmation with the backup filename.

**Flags:**

- `--note "text"` — attach a human-readable note
- `--tag {manual,auto}` — override the default tag (default: `manual` when run interactively, `auto` when run via scheduler)
- `--quiet` — suppress output (for cron/scheduled task use)

**Retention:** configurable in `config.toml`. Default: keep last 100 backups. Oldest are pruned on each new backup. `auto`-tagged backups are pruned independently from `manual` ones (so automated backups don't push out your manual ones).

### `pathkeeper restore`

Restores PATH from a previous backup.

**Interactive flow:**

1. List recent backups (most recent first), showing timestamp, tag, note, and entry count.
2. User selects one.
3. Show a **diff** between current PATH and the selected backup (added entries in green, removed in red, reordered in yellow).
4. Ask which scope to restore: system, user, or both.
5. **Automatically create a `pre-restore` backup** of the current state.
6. Confirm, then write.

**Direct invocation:**

```
pathkeeper restore <backup-file-or-timestamp>
    [--scope {system,user,all}]
    [--no-pre-backup]
    [--force]           # skip confirmation
    [--dry-run]         # show diff only, don't write
```

**Write mechanism:**

| OS | System PATH | User PATH |
| --- | --- | --- |
| Windows | Write to registry via `winreg.SetValueEx` with `REG_EXPAND_SZ`. Broadcast `WM_SETTINGCHANGE`. Requires admin. | Same, `HKCU`. No admin needed. |
| macOS | Write to `/etc/paths` (requires `sudo`). | Rewrite the appropriate shell rc file's PATH export block (delimited by `# --- pathkeeper managed ---` markers). |
| Linux | Write to `/etc/environment` or `/etc/profile.d/pathkeeper.sh` (requires `sudo`). | Same marker-delimited block in shell rc file. |

On macOS/Linux, `pathkeeper` only manages PATH lines within its own marker block. It never touches other content in shell rc files.

### `pathkeeper dedupe`

Removes duplicate and optionally invalid entries from PATH.

**Interactive flow:**

1. Show current PATH with duplicates and invalids highlighted.
2. Offer three modes:
   - **Duplicates only** — remove later occurrences, keep first.
   - **Invalid only** — remove entries pointing to nonexistent directories.
   - **Both** (default).
3. Show preview of what will be removed.
4. Create `pre-dedupe` backup.
5. Confirm, then write.

**Direct invocation:**

```
pathkeeper dedupe
    [--scope {system,user,all}]
    [--keep {first,last}]           # which duplicate to keep (default: first)
    [--remove-invalid]              # also remove nonexistent dirs (default: true)
    [--no-remove-invalid]
    [--dry-run]
    [--force]
```

**Case sensitivity:** On Windows, path comparison is case-insensitive. On macOS, case-insensitive by default (HFS+/APFS). On Linux, case-sensitive.

**Trailing separators:** `C:\foo\` and `C:\foo` are treated as the same entry. `/usr/bin/` and `/usr/bin` likewise.

### `pathkeeper populate`

Scans the system for common tool directories and offers to add missing ones to PATH. Inspired by WindowsPathFix's auto-discovery.

**Behavior:**

1. Load the known-tools catalog (`known_tools.toml` — ships with sensible defaults, user-editable).
2. For each candidate directory pattern, check if it exists on disk.
3. Filter out any that are already in PATH.
4. Present the discoveries grouped by category, with checkboxes:

```
Found 12 tool directories not in your PATH:

  Programming Languages
    [x] C:\Python312\Scripts          (Python 3.12)
    [x] C:\Program Files\Go\bin       (Go)
    [ ] C:\Ruby33-x64\bin             (Ruby)

  Developer Tools
    [x] C:\Program Files\Git\cmd      (Git)
    [x] C:\Program Files\Docker\...   (Docker)

  Databases
    [ ] C:\Program Files\PostgreSQL\16\bin

  (a) Select all  (n) Select none  (Enter) Confirm
```

5. Create `pre-populate` backup.
6. Add selected entries to user PATH (not system, unless `--system` is passed).

**Direct invocation:**

```
pathkeeper populate
    [--scope {system,user}]       # where to add (default: user)
    [--all]                       # add all found without prompting
    [--category CATEGORY]         # only scan a specific category
    [--dry-run]
    [--list-catalog]              # print the known-tools catalog and exit
```

**Known-tools catalog structure** (`known_tools.toml`):

```toml
# Each entry is a search pattern. Glob wildcards allowed.
# os = which OSes this applies to (windows, darwin, linux, or all)

[[tools]]
name = "Python"
category = "Programming Languages"
os = "windows"
patterns = [
    "C:\\Python3*",
    "C:\\Python3*\\Scripts",
    "%LOCALAPPDATA%\\Programs\\Python\\Python3*",
    "%LOCALAPPDATA%\\Programs\\Python\\Python3*\\Scripts",
]

[[tools]]
name = "Homebrew"
category = "Package Managers"
os = "darwin"
patterns = [
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
]

[[tools]]
name = "Go"
category = "Programming Languages"
os = "all"
patterns = [
    # Windows
    "C:\\Program Files\\Go\\bin",
    "C:\\Go\\bin",
    # Unix
    "/usr/local/go/bin",
    "$HOME/go/bin",
]
```

The default catalog should ship with patterns for at least: Python, Node.js, Go, Rust/Cargo, Ruby, Java/JDK, .NET, PHP, Dart, Git, Docker, kubectl, Terraform, VS Code, PostgreSQL, MySQL, MongoDB, SQLite, Homebrew, Snap, Flatpak, Composer, Maven, Gradle, and Deno.

### `pathkeeper edit`

Interactive PATH editor.

**Interface:**

```
Editing USER PATH (8 entries):

  1. C:\Users\matt\.cargo\bin         ✓
  2. C:\Users\matt\AppData\...\npm    ✓
  3. C:\Python312\Scripts              ✓
  4. C:\Python312                      ✓
  5. C:\old\removed\thing              ✗
  6. C:\Users\matt\go\bin              ✓
  7. C:\Users\matt\.cargo\bin          D (duplicate of #1)
  8. C:\Program Files\Git\cmd          ✓

Commands:
  [a]dd <path>         — Add a new entry
  [d]elete <n>         — Remove entry by number
  [m]ove <n> <pos>     — Move entry to position
  [e]dit <n> <newpath> — Replace entry in-place
  [s]wap <n> <m>       — Swap two entries
  [u]ndo               — Undo last change
  [r]eset              — Revert all changes (back to current PATH)
  [p]review            — Show diff from original
  [w]rite              — Save changes and exit
  [q]uit               — Discard changes and exit

edit>
```

**Behavior:**

- All changes are staged in memory. Nothing is written until `[w]rite`.
- Create `pre-edit` backup before writing.
- Scope selection: prompt for system vs. user at entry (or pass `--scope`).
- On write, show a final diff and confirmation.

**Direct invocation (non-interactive):**

```
pathkeeper edit --add "/usr/local/newbin" [--scope user] [--position 0]
pathkeeper edit --remove "/old/path"      [--scope user]
pathkeeper edit --move "/some/path" --position 3
```

---

## Configuration

`~/.pathkeeper/config.toml`:

```toml
[general]
# How many backups to retain
max_backups = 100
# Separate limits by tag
max_auto_backups = 50
max_manual_backups = 50

[display]
# Use color in output (auto-detected if omitted)
color = true
# Use unicode status symbols (✓ ✗ ⚠) or ASCII (ok, !, ~)
unicode = true

[restore]
# Always create a pre-restore backup (recommended)
pre_backup = true

[populate]
# Path to custom tools catalog (merged with built-in)
extra_catalog = ""

[schedule]
# For `pathkeeper schedule` — see Scheduling section
enabled = false
interval = "1h"

[shell]
# Override shell rc file for Unix PATH writes
# If empty, auto-detected from $SHELL
rc_file = ""
```

---

## Scheduling (Optional Feature)

`pathkeeper schedule` installs a recurring backup job appropriate to the OS:

| OS | Mechanism |
| --- | --- |
| Windows | Task Scheduler (`schtasks`) |
| macOS | `launchd` plist in `~/Library/LaunchAgents/` |
| Linux | systemd user timer, or crontab fallback |

```
pathkeeper schedule install [--interval 1h]
pathkeeper schedule remove
pathkeeper schedule status
```

The scheduled job runs `pathkeeper backup --tag auto --quiet`.

---

## Architecture

### Module Layout

```
pathkeeper/
├── __init__.py
├── __main__.py              # Entry point: `python -m pathkeeper`
├── cli.py                   # Argument parsing (argparse), dispatch
├── interactive.py           # Interactive menu loop
├── core/
│   ├── __init__.py
│   ├── path_reader.py       # Read PATH from OS-specific sources
│   ├── path_writer.py       # Write PATH back to OS-specific targets
│   ├── backup.py            # Create/list/load/prune backups
│   ├── diff.py              # Compute and display PATH diffs
│   ├── dedupe.py            # Deduplication and validation logic
│   ├── populate.py          # Tool discovery from catalog
│   └── edit.py              # Edit session state machine
├── platform/
│   ├── __init__.py
│   ├── windows.py           # winreg reads/writes, WM_SETTINGCHANGE broadcast
│   ├── macos.py             # /etc/paths, shell rc management
│   └── linux.py             # /etc/environment, shell rc management
├── catalog/
│   └── known_tools.toml     # Default tool patterns
└── config.py                # Config loading/defaults
```

### Platform Abstraction

`path_reader.py` and `path_writer.py` define a `Protocol`:

```python
class PathReader(Protocol):
    def read_system_path(self) -> list[str]: ...
    def read_user_path(self) -> list[str]: ...
    def read_system_path_raw(self) -> str: ...
    def read_user_path_raw(self) -> str: ...

class PathWriter(Protocol):
    def write_system_path(self, entries: list[str]) -> None: ...
    def write_user_path(self, entries: list[str]) -> None: ...
```

A factory selects the correct implementation based on `sys.platform`.

### Dependencies

**Required (stdlib only for core):**

- `winreg` (Windows, stdlib)
- `json`, `tomllib` (stdlib, Python 3.11+; `tomli` backport for 3.10)
- `argparse`, `pathlib`, `os`, `platform`, `datetime`, `shutil`

**Optional (for enhanced TUI):**

- `rich` — colored/formatted terminal output. Graceful fallback to plain text if not installed.

No other third-party dependencies. The tool should be installable with `pip install pathkeeper` or runnable as `python -m pathkeeper` from a git clone.

---

## Safety Principles

1. **Never write without a backup.** Every mutating operation (`restore`, `dedupe`, `populate`, `edit --write`) creates an automatic pre-operation backup unless explicitly opted out.
2. **Never write without confirmation.** All interactive write operations require explicit confirmation. Direct CLI invocation requires `--force` to skip.
3. **Show before writing.** Every mutating operation shows a diff/preview before asking for confirmation.
4. **Preserve raw values.** On Windows, preserve `REG_EXPAND_SZ` type and unexpanded `%VARIABLES%`. Never silently expand environment variables when round-tripping.
5. **Don't touch what you don't own.** On macOS/Linux, only edit PATH lines within `pathkeeper`'s own marker block in shell rc files. Never modify other content.
6. **Elevation is explicit.** If an operation requires admin/sudo (system PATH writes), tell the user clearly and fail gracefully rather than silently requesting elevation.

---

## Exit Codes

| Code | Meaning |
| --- | --- |
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Permission denied (needs elevation) |
| 4 | Backup not found |
| 5 | User cancelled |

---

## Future Considerations (Out of Scope for v0.1)

- **Registry change watcher** — use `RegNotifyChangeKeyValue` on Windows to detect PATH changes in real time and auto-backup.
- **Filesystem watcher** — inotify/FSEvents on Unix to detect changes to `/etc/paths` or shell rc files.
- **GUI** — a TUI (textual) or web-based interface.
- **Diff between two arbitrary backups** — `pathkeeper diff <backup1> <backup2>`.
- **Import/export** — ingest `.reg` files from Wargo's Path Backup & Restore or WindowsPathFix backup formats.
- **PATH linting rules** — configurable warnings (e.g., "user PATH should not contain system directories", "PATH entry points to a file not a directory").
