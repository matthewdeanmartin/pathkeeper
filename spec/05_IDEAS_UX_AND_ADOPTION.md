# pathkeeper — Ideas: UX & Adoption

Ideas for making pathkeeper easier to discover, easier to use for the first
time, and more likely to become a habit.

---

## First-run experience

### Interactive onboarding wizard

When pathkeeper is run for the first time (no `~/.pathkeeper/` exists),
offer a short wizard instead of dropping into the main menu:

1. Welcome + brief explanation of what pathkeeper does
2. Run a quick PATH health check and show the summary
3. Offer to create an initial backup right now
4. Offer to install the shell startup hook
5. Optionally run populate to find missing tool directories
6. Done — show what was set up and how to run `pathkeeper` again

Why it could help:

- First-run is the moment of highest motivation and highest confusion
- A five-step wizard captures value immediately
- Users who create a first backup are much more likely to keep using the tool
- Could be triggered by detecting `~/.pathkeeper/` is absent

---

### `pathkeeper doctor` as the default for new users

For users with zero backups, the current interactive menu shows "No backups
available yet" in the Restore slot and proceeds normally.  A stronger default:

- When there are zero backups, make Doctor the default on first launch instead
  of the full menu
- Show the health summary prominently
- Offer "Create first backup" and "Set up automatic backups" as the two primary
  actions

Why it could help:

- New users don't know what they have — doctor tells them before they invest in backups
- Framing the first action as "diagnose" rather than "backup" is more compelling

---

### "What just broke?" mode

A quick-entry command for the panicked user: `pathkeeper triage`.  Sequence:

1. Compare current PATH to the most recent backup
2. If they differ, show the diff and offer to restore
3. If they are the same, run doctor and show problems
4. If no backups exist, run repair-truncated and populate as first steps

Why it could help:

- Users with a broken PATH are stressed and don't know where to start
- `pathkeeper triage` is more discoverable than knowing the specific subcommand
- Could become the tool's "elevator pitch" entry point

---

## Interactive menu improvements

### Inline health indicators in the menu

Show a small status badge next to each menu item when the action is especially
recommended:

```
  [2]  Doctor  Diagnose problems and suggest repairs  [3 issues]
  [7]  Dedupe  Remove duplicates and broken entries   [2 dupes]
```

Why it could help:

- Users see at a glance what needs attention without running every command
- Reduces the cognitive load of the "what should I do next?" question
- The data is already computed in the startup banner — just needs to flow into the menu

---

### Recent action history in the menu footer

Show the last 2-3 pathkeeper actions in a footer at the bottom of the menu:

```
  Recent:  backup (auto, 3m ago)  ·  dedupe (2025-03-20)
```

Why it could help:

- Gives context for "what did I last do?" without leaving the menu
- Particularly useful if a user returns after a few days
- Could highlight if no backup has been created in a long time

---

### Menu filtering / search

For users who know what they want: type a partial command name and jump directly.

```
  > pop[Enter]  → jumps to Populate
```

Why it could help:

- Power users are slowed down by scrolling through 12 items
- Makes the tool feel faster as users become more experienced
- Low implementation cost: just prefix-match the label

---

### Breadcrumb / context line during sub-commands

When a handler is running interactively, show a persistent context line:

```
  [Dedupe] scope=all  keep=first
  ─────────────────────────────────
```

Why it could help:

- Users lose track of what they started when commands print a lot of output
- Especially useful for repair and populate where many prompts follow
- One extra print per command entry — minimal cost

---

## Output and readability

### Wide terminal auto-detection for the backup table

The `backups list` table currently has a fixed max_width of 220.  It should:

- Auto-detect terminal width via `shutil.get_terminal_size()`
- Truncate long paths in the Backup column gracefully
- Shrink or hide the Note column when terminal is narrow

Why it could help:

- The table is unreadable at 80 columns (most default terminals)
- Wide users get full benefit; narrow users get usable output
- No new dependencies — `shutil.get_terminal_size` is stdlib

---

### Paged output for long lists

When `backups list` or `inspect` produces output longer than the terminal
height, offer to page it:

```
  -- 42 entries, press [Enter] for more, [q] to stop --
```

Or honor `$PAGER` and pipe through it automatically.

Why it could help:

- Users with large PATHs or long backup histories scroll past the top
- Pager support is expected behavior in CLI tools
- Could honor `NO_PAGER` env var for scripted use

---

### Color in non-TTY mode (for CI with color support)

Currently color is suppressed for non-TTY stdout.  Some CI systems (GitHub
Actions, GitLab CI) support ANSI color via `$FORCE_COLOR` or
`$GITHUB_ACTIONS`.  Honor these:

- `FORCE_COLOR=1` or `FORCE_COLOR=true` — enable color regardless of TTY
- `GITHUB_ACTIONS=true` — enable color (GitHub strips color if not supported)
- `COLORTERM=truecolor` — enable full 24-bit color if desired

Why it could help:

- Doctor output in CI PRs is much easier to read with color
- The `NO_COLOR` standard already handles the "disable" case; this handles "force on"
- One extra env check in `Theme._autodetect()`

---

## Discoverability and help

### `pathkeeper help <command>` with examples

Each command's `--help` output should include 2-3 concrete usage examples:

```
Examples:
  pathkeeper backup --note "before installing VS Code"
  pathkeeper backup --tag auto --quiet
  pathkeeper backup --dry-run
```

Why it could help:

- `--help` is often the only documentation a user reads
- Examples communicate intent better than flag descriptions alone
- Low cost: just add to the `epilog` of each subparser

---

### `pathkeeper doctor --explain`

An extended doctor mode that adds a plain-language sentence to each finding:

```
  [x]  C:\Python310  missing
       This directory no longer exists. Python 3.10 may have been
       uninstalled or moved. Consider removing this entry or running
       pathkeeper populate to find the new Python location.
```

Why it could help:

- The current output shows what is wrong but not why it matters
- New users don't know whether a missing entry is a problem or just stale
- Could be the default in interactive mode, opt-in in scripted mode

---

### Shell completion

Generate tab completions for bash, zsh, fish, and PowerShell.  argparse has
no built-in completion generator, but the `shtab` package or a hand-rolled
approach would work.

Completions for:

- Subcommand names
- `--scope` values (`system`, `user`, `all`)
- Backup identifiers (complete from `~/.pathkeeper/backups/*.json`)

Why it could help:

- Tab completion is expected by power users
- Backup identifier completion is particularly useful (no one memorizes timestamps)
- Makes the tool feel polished

---

### `pathkeeper update-catalog`

Fetch the latest `known_tools.toml` from a URL (configurable, defaults off)
and merge it with the user's copy, preserving any local additions.

Why it could help:

- The catalog will grow stale as new tools appear
- A pull-to-update story makes the catalog a living resource
- Merge strategy: add new entries, never remove user-added entries

Security considerations:

- Must be opt-in, never automatic
- Should verify a checksum or signature before applying
- URL should be configurable so organizations can host their own

---

## Adoption and sharing ideas

### One-line install check command

`pathkeeper selfcheck` — verify that the pathkeeper installation is working:

- Check that the backup directory exists and is writable
- Check that the catalog is present and parseable
- Check that the platform adapter can read PATH
- Check that auto backup is configured (startup hook or schedule)
- Print pass/fail for each check with a summary exit code

Why it could help:

- Useful after install to confirm everything is wired up
- Makes support easier: "run selfcheck and paste the output"
- Could be part of the first-run wizard

---

### Anonymous usage telemetry (opt-in)

Offer opt-in telemetry that reports:

- Command used (not arguments)
- OS and Python version
- Backup count range (0, 1-10, 11-50, 50+)
- Health summary counts (no PATH content)

Why it could help:

- Would reveal which commands are actually used vs. never touched
- OS distribution data would inform platform priority
- Must be strictly opt-in, clearly disclosed, and easy to disable

---

## Potential next candidates

If only a few of these move forward soon, these seem especially strong:

1. `pathkeeper triage` — high-value entry point for broken-PATH users
2. `pathkeeper help <command>` with examples — zero-cost discoverability win
3. Wide terminal auto-detection for the backup table — fixes a real usability gap
4. Inline health indicators in the menu — leverages already-computed data
5. Interactive onboarding wizard — converts installs into retained users
6. Shell completion — marks the tool as mature and serious
