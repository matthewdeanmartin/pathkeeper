# Commands

This page describes the commands exposed by the current CLI implementation.

## `pathkeeper`

Run with no arguments to open the interactive menu:

```bash
uv run pathkeeper
```

The menu currently offers shortcuts into inspect, doctor, creating backups, listing backups, showing backups, restore, dedupe, populate, edit, repair-truncated, and schedule status.

When the interactive menu starts, it shows the backup directory and a one-line PATH health summary derived from the current `inspect` report.

If you cancel an interactive command at a confirmation prompt, pathkeeper returns to the menu instead of exiting the application.

Use the global logging switch to control log verbosity:

```bash
uv run pathkeeper --log-level info doctor
```

## `pathkeeper inspect`

Inspect PATH entries and show their status.

```bash
uv run pathkeeper inspect [--scope {system,user,all}] [--json] [--only-invalid] [--only-dupes]
```

Status markers in text output:

- `ok`: existing directory
- `x`: missing entry
- `~`: existing path that is a file rather than a directory
- `D`: duplicate entry
- `!`: empty entry

## `pathkeeper doctor`

Diagnose PATH issues and print recommendations.

```bash
uv run pathkeeper doctor [--scope {system,user,all}] [--json] [--only-invalid] [--only-dupes]
```

`doctor` uses the same diagnostics engine as `inspect` but also prints follow-up suggestions.

## `pathkeeper backup`

Create a backup of the current PATH state.

```bash
uv run pathkeeper backup [--note "text"] [--tag {manual,auto}] [--quiet] [--force] [--dry-run]
```

Backups are stored as JSON in `~/.pathkeeper/backups/`.

By default, `backup` skips creating a new file when the latest saved backup has identical PATH content. Use `--force` to override that behavior.

Use `--dry-run` to preview whether a backup would be created or skipped.

## `pathkeeper backups`

Browse saved snapshots.

```bash
uv run pathkeeper backups list
uv run pathkeeper backups show [backup-file-or-prefix-or-index]
```

`backups list` prints the most recent snapshots in a table, including a content hash so repeated snapshots are easy to spot. Timestamps are shown in compact UTC minute precision.

`backups show` prints metadata and the saved system and user PATH entries. If you omit the identifier, it shows the 20 most recent backups and prompts for a numbered selection. You can also pass a list index such as `2` instead of a full filename.

## `pathkeeper restore`

Restore a previous snapshot.

```bash
uv run pathkeeper restore <backup-file-or-prefix> [--scope {system,user,all}] [--no-pre-backup] [--force] [--dry-run]
```

`restore` prints a diff first. By default it also creates a `pre-restore` backup before writing.

## `pathkeeper dedupe`

Remove duplicate entries and, by default, invalid directories.

```bash
uv run pathkeeper dedupe [--scope {system,user,all}] [--keep {first,last}] [--remove-invalid] [--no-remove-invalid] [--dry-run] [--force]
```

## `pathkeeper populate`

Discover likely tool directories from the bundled catalog.

```bash
uv run pathkeeper populate [--scope {system,user}] [--category CATEGORY] [--dry-run] [--list-catalog] [--all] [--force]
```

Current behavior:

- `--list-catalog` prints the merged tool catalog and exits
- without `--dry-run`, discovered entries are added to the selected scope after confirmation
- `--all` is useful when you want non-interactive confirmation for the full discovered set
- for versioned tool families such as Python and Node.js, `populate` prefers the latest discovered version instead of proposing every older install

## `pathkeeper edit`

Launch the staged PATH editor. In the interactive menu, choosing `Edit` now opens the editor workflow directly instead of just printing the current entries.

```bash
uv run pathkeeper edit [--scope {system,user}] [--add PATH] [--remove PATH] [--move PATH --position N] [--edit OLD --new-path NEW] [--force] [--dry-run]
```

Examples:

```bash
uv run pathkeeper edit --add "/usr/local/newbin" --force
uv run pathkeeper edit --remove "/old/tool/bin" --force
uv run pathkeeper edit --move "/usr/local/bin" --position 0 --force
uv run pathkeeper edit --edit "/bad/path" --new-path "/good/path" --force
```

Within the editor you can add, delete, move, replace, preview, undo, reset, write, or quit staged changes.

For direct invocation, `--dry-run` prints the staged diff without writing changes.

## `pathkeeper repair-truncated`

Detect likely truncated PATH entries and suggest full replacements.

```bash
uv run pathkeeper repair-truncated [--scope {system,user,all}] [--dry-run] [--force]
```

Current behavior:

- only invalid entries that look like truncated path suffixes are considered
- backup history is searched first for matching full directories
- if backup history does not yield a match, likely disk roots are searched for directories whose trailing path matches the broken entry
- when there is one candidate, pathkeeper offers to apply it
- when there are multiple candidates, pathkeeper asks you which one to use
- before writing, pathkeeper shows a diff and creates a safety backup
- in the interactive menu, `Repair truncated` uses the same guided selection flow

## `pathkeeper schedule`

Manage scheduled automatic backups.

```bash
uv run pathkeeper schedule status
uv run pathkeeper schedule install [--interval startup|60m] [--trigger startup|logon] [--dry-run]
uv run pathkeeper schedule remove [--dry-run]
```

When scheduling is not configured, `schedule status` now reports that it is disabled without exposing low-level missing-file errors.

In the interactive menu, choosing `Schedule status` offers to install automatic backups immediately.

On Windows, if creating a startup task is denied because the shell is not elevated, the interactive flow explains the issue and offers a per-user logon task fallback.

If Windows also denies creation of the per-user logon task, the interactive flow now reports that clearly and tells you to retry from an elevated shell or check whether Task Scheduler is blocked by policy.

In the interactive menu, choosing `Dedupe` on Windows now offers to retry against the user PATH only when system-scope cleanup needs elevation but user-scope cleanup is still possible.

For scheduler writes, `--dry-run` shows what would be installed or removed without touching Task Scheduler, launchd, or systemd files.

Platform behavior:

- Windows uses Task Scheduler
- macOS writes a launchd agent
- Linux writes systemd user timer files

## `pathkeeper locate`

Find an executable anywhere on the computer.

```bash
uv run pathkeeper locate <name> [--all] [--drive DRIVE]
```

`locate` is a "fancy which" that searches likely tool locations first, then performs a deep search across the filesystem using the fastest available tools (`ripgrep`, `fd`, `mdfind`, `locate`, or a Python fallback).
