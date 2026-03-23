# pathkeeper

`pathkeeper` is a typed Python CLI for backing up, inspecting, diagnosing, restoring, and repairing the PATH environment
variable. When a bad installer, shell tweak, or system tool mangles PATH, pathkeeper gives you a reliable way to
recover.

## Installation

```bash
pipx install pathkeeper
```

Or any other global installation method.

## Quick start

```bash
# Interactive menu
pathkeeper

# GUI
pathkeeper gui
```

## Scenarios

### Diagnose your PATH

```bash
# Checklist view — shows every check with PASS / FAIL / WARN
pathkeeper doctor

# Same, with plain-language explanation for each finding
pathkeeper doctor --explain

# Full entry listing with status markers
pathkeeper inspect

# Show only invalid (missing / not-a-directory) entries
pathkeeper inspect --only-invalid

# Show only duplicate entries
pathkeeper inspect --only-dupes

# JSON output (machine-readable)
pathkeeper doctor --json
pathkeeper inspect --json
```

### Back up and restore

```bash
# Create a backup (skips if content is unchanged)
pathkeeper backup

# Always create a backup, even if nothing changed
pathkeeper backup --force

# Attach a note
pathkeeper backup --note "before installing toolchain"

# Preview what would be backed up
pathkeeper backup --dry-run

# List recent backups
pathkeeper backups list

# Inspect a specific backup
pathkeeper backups show          # pick interactively
pathkeeper backups show 2        # backup #2 from the list

# Compare a backup against the live PATH
pathkeeper diff-current          # latest backup vs current
pathkeeper diff-current 2        # backup #2 vs current
pathkeeper diff-current 2025-03-05   # timestamp prefix vs current

# Compare two backups against each other
pathkeeper diff 1 2

# Restore a backup
pathkeeper restore 2025-03-05T14-30-00 --dry-run  # preview
pathkeeper restore 2025-03-05T14-30-00             # apply
pathkeeper restore 2 --scope user                  # user PATH only
```

### Clean up PATH

```bash
# Remove duplicates and invalid entries (preview first)
pathkeeper dedupe --dry-run
pathkeeper dedupe

# Remove duplicates only (keep invalid entries)
pathkeeper dedupe --no-remove-invalid

# Repair likely truncated entries (setx damage, etc.)
pathkeeper repair-truncated --dry-run
pathkeeper repair-truncated
```

### Discover and add tools

```bash
# Preview what would be added
pathkeeper populate --dry-run

# Interactive selection by category
pathkeeper populate

# Add everything found
pathkeeper populate --all

# Add only a specific category
pathkeeper populate --category python

# Show the tool catalog
pathkeeper populate --list-catalog
```

### Inspect shadows and runtime additions

```bash
# Show executables that shadow each other across PATH directories
pathkeeper shadow

# Show PATH entries injected at runtime (not from registry / rc files)
pathkeeper runtime-entries
```

### Edit PATH directly

```bash
# Interactive staged editor
pathkeeper edit

# Add / remove / move entries non-interactively
pathkeeper edit --add "/usr/local/newbin" --dry-run
pathkeeper edit --add "/usr/local/newbin" --force
pathkeeper edit --remove "/usr/local/oldbin"
pathkeeper edit --move "/usr/local/bin" --position 1
```

### Automate backups

```bash
# Install a scheduled backup task (Task Scheduler / launchd / systemd)
pathkeeper schedule install
pathkeeper schedule install --trigger logon   # Windows per-user logon task
pathkeeper schedule status
pathkeeper schedule remove

# Or inject a backup command into your shell startup file
pathkeeper shell-startup
pathkeeper shell-startup --shell bash --dry-run
pathkeeper shell-startup --remove
```

### Verify your installation

```bash
# Run pathkeeper's own health checks (useful when reporting bugs)
pathkeeper selfcheck
```

______________________________________________________________________

## What it checks

`pathkeeper doctor` runs a checklist that includes:

- Duplicate entries
- Missing / invalid directories
- Files in PATH (not directories)
- Empty entries (stray separators)
- Missing separators (glued paths like `/usr/local/bin/usr/bin`)
- Unresolvable variables (`%FOO%` / `$FOO` that are not defined)
- PATH length (Windows: setx 2047-char limit, registry 32767-char limit)
- setx truncation sentinel (PATH exactly 1023 or 1024 chars — classic damage sign)

______________________________________________________________________
