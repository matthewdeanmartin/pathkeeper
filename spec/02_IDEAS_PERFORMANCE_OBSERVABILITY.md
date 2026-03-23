# pathkeeper — Ideas: Performance & Observability

Fresh ideas generated after implementing startup benchmarking and lazy imports.
These are exploratory, not committed requirements.

______________________________________________________________________

## Performance ideas

### Startup skip fast-path (skip config load)

The current `backup --quiet --tag auto` startup path loads config before
checking whether PATH changed. If we stored a hash of the last-seen PATH
in a tiny sentinel file (`~/.pathkeeper/last_hash`), we could bail out
before even opening `config.toml` in the common case where nothing changed.

Why it could help:

- Would cut the startup path from ~6 ms to sub-millisecond for unchanged PATH
- Config load + TOML parse is the dominant cost on the in-process skip path
- Sentinel file is a single file read + compare, no JSON parsing

Risks / considerations:

- Sentinel must be invalidated when PATH actually changes
- On Windows the registry read is still needed to compute the hash — but
  the registry cache we already added means it costs one `OpenKey` per scope
- Could make the tool appear to "miss" a change if the sentinel is stale;
  needs a TTL or force-invalidation story

______________________________________________________________________

### Warm-cache backup index

`list_backups()` currently globs and parses every JSON file in the backup
directory. A small index file (`~/.pathkeeper/index.json`) that stores
just `{filename, timestamp, tag, hash}` per backup would let common queries
(latest backup, recent list, duplicate check) skip full JSON parsing.

Why it could help:

- Users with hundreds of backups pay O(n) parse cost today
- The interactive startup banner calls `list_backups` to count backups — this
  could be free
- Backup listing (`backups list`) would be near-instant

Risks / considerations:

- Index can become stale if backup files are moved/deleted manually
- Must be kept consistent on write; need atomic update strategy
- Could detect staleness by comparing glob results against index entries

______________________________________________________________________

### Lazy config singleton

`load_config()` is called in `_backup_now`, `_init_theme`, and then again
inside handlers like `_restore`, `_dedupe`, etc. Within a single invocation
the config never changes. A module-level `functools.cache` on `load_config`
would read `config.toml` once and return the same object on repeat calls.

Why it could help:

- Eliminates redundant TOML parses in multi-step interactive flows
- Zero behavior change — config is immutable per invocation
- Two-line change

______________________________________________________________________

### `--perf` flag for startup profiling

Add a hidden `--perf` flag that prints timing breakdowns for each phase of
the `backup` command: config load, registry read, backup dir scan, write.

Why it could help:

- Makes future regressions easy to diagnose without running a profiler
- Helps users self-diagnose if startup feels slow (network drive, antivirus)
- Pairs naturally with the benchmark suite

______________________________________________________________________

## Observability ideas

### Structured backup event log

Append a line to `~/.pathkeeper/events.jsonl` for every meaningful action:
backup created, backup skipped, entry added, restore applied, prune removed N
files. Each line is a JSON object with timestamp, action, and key metadata.

Why it could help:

- Gives users a lightweight audit trail without inspecting individual backup files
- Makes it easy to answer "when did I last actually change anything?"
- Could power a future `pathkeeper log` command or dashboard widget
- Useful for support: users can share the log instead of every backup file

______________________________________________________________________

### Backup size and growth tracking

Track total backup directory size in the event log and warn when it crosses a
configurable budget (default: 50 MB).

Why it could help:

- Users on machines with constrained home directories get early warning
- Auto backups can quietly consume space if PATH is large or changes often
- Pairs well with the existing `prune_backups` story

______________________________________________________________________

### `pathkeeper status` one-liner

A new `status` command (also accessible via a shell alias hook) that prints a
single summary line suitable for embedding in a shell prompt or status bar:

```
pathkeeper: 42 backups, PATH healthy (32 entries, 0 invalid, 0 dup)
```

Or in structured form:

```
pathkeeper status --json
{"backups": 42, "valid": 32, "invalid": 0, "duplicates": 0, "health": "ok"}
```

Why it could help:

- Shell prompt integrations (Starship, Powerlevel10k, Oh My Posh) could surface
  PATH health at a glance
- CI pipelines could assert PATH health as a post-install check
- Much faster than `inspect` or `doctor` — only reads the latest backup hash
  and skips full path analysis when PATH is unchanged

______________________________________________________________________

### `pathkeeper doctor --ci` exit codes

Give `doctor` a `--ci` flag that maps health states to meaningful exit codes:

- `0` — healthy
- `1` — warnings only (duplicates, empty entries)
- `2` — errors (missing directories, files on PATH)
- `3` — critical (truncated PATH, PATH length near OS limit)

Why it could help:

- Makes `pathkeeper doctor --ci` a drop-in pre-flight check in onboarding scripts
- CI pipelines can gate on PATH health without parsing output
- Complements the existing `--json` flag for machine consumption

______________________________________________________________________

## Diff and change attribution ideas

### Diff between any two backups

`pathkeeper diff <backup-a> <backup-b>` — show what changed between two
arbitrary snapshots, not just between current PATH and a backup.

Why it could help:

- Lets users see what an installer changed: diff pre-install vs post-install
- Useful for debugging "when did `C:\foo` appear?" by bisecting the history
- Could detect regressions if PATH is tested on CI

______________________________________________________________________

### Change attribution in diff output

When showing a diff, annotate each changed entry with the most likely source:
`(new — not in any previous backup)`, `(restored from 2025-03-01)`,
`(was present until 2025-02-28)`.

Why it could help:

- Turns a raw diff into an explanation rather than just a list
- Particularly helpful for understanding what an installer changed
- Leverages the existing backup history for free

______________________________________________________________________

### Installer session detector

Watch for rapid sequences of PATH changes (multiple changes within a short
window) and tag them as a probable installer session. Group the changes into
one event in the log: "Installer session: added 4 entries, removed 1".

Why it could help:

- Common cause of PATH problems is an installer writing to PATH and failing
- Grouping makes the history easier to read
- Could drive a "roll back this installer session" restore option

______________________________________________________________________

## Safety and trust ideas

### Backup verification / integrity check

`pathkeeper verify` — read every backup file and confirm it is valid JSON,
has the expected schema, and that the stored hash matches the content.

Why it could help:

- Gives confidence before relying on a restore
- Could catch disk corruption or accidental truncation early
- Useful as a scheduled self-check alongside `backup --tag auto`

______________________________________________________________________

### Backup signing (optional)

Optionally sign backup files with an HMAC using a user-supplied key stored
in the OS keychain / credential manager. Verification confirms the file was
not tampered with.

Why it could help:

- Matters in shared environments where other users might access the home directory
- Makes backups trustworthy for compliance or forensic scenarios
- HMAC-SHA256 with stdlib `hmac` — no new dependencies

______________________________________________________________________

### Dry-run default mode

A config option `general.require_confirm = true` that makes all mutating
commands behave as `--dry-run` unless `--force` is also passed.

Why it could help:

- Gives cautious users extra protection against accidental writes
- Particularly useful when running pathkeeper as part of a larger automation
- Easy to override for scripted flows

______________________________________________________________________

### Immutable backup retention window

A config option `general.immutable_hours = 24` that prevents pruning of
backups younger than N hours regardless of the max_backups limits.

Why it could help:

- Protects very recent backups even if many auto backups accumulate quickly
- Gives users a recovery window after an installer runs
- Complements max_auto_backups without replacing it

______________________________________________________________________

## Integration ideas

### Git hooks integration

`pathkeeper backup --tag git-pre-commit` as a git pre-commit hook. Could be
installed automatically via `pathkeeper git-hook install`.

Why it could help:

- Every git commit becomes a potential PATH state checkpoint
- Particularly useful in development environments where tooling is installed frequently
- git log provides natural context for "what was I doing when PATH changed?"

______________________________________________________________________

### VS Code / editor extension hook

An optional hook that runs `pathkeeper backup --quiet --tag vscode-startup`
when VS Code (or another editor) launches.

Why it could help:

- VS Code extensions and Dev Containers commonly mutate PATH
- Gives a backup before every session, not just every shell startup
- Could be triggered via VS Code's `tasks.json` or a workspace setting

______________________________________________________________________

### `pathkeeper export` for dotfiles repos

Export the current user PATH as a shell snippet suitable for inclusion in a
dotfiles repo:

```bash
# Generated by pathkeeper export on 2025-03-22
export PATH="$HOME/.cargo/bin:$HOME/go/bin:$PATH"
```

Or as a PowerShell profile snippet on Windows.

Why it could help:

- Bridges the gap between pathkeeper's backup store and dotfiles management
- Gives users a portable representation they can commit alongside their configs
- Could include comments noting which entries were added by which tool

______________________________________________________________________

### `pathkeeper import` from dotfiles

The inverse: read a shell `export PATH=...` line or a `.env` style file and
merge entries into the current user PATH, with dedup and validation.

Why it could help:

- Useful when bootstrapping a new machine from a dotfiles repo
- Gives a reviewable preview before writing
- Pairs with `populate` for a complete new-machine setup story

______________________________________________________________________

## Quality-of-life ideas

### Interactive backup notes

When running `pathkeeper backup` interactively (no `--note`), prompt for an
optional note before writing. Pre-fill with a timestamp and detected context
like "before install session" or "manual — no context detected".

Why it could help:

- Notes dramatically improve the usefulness of the backup list
- Users rarely remember to pass `--note` manually
- Could detect context from recent process list (Windows) or shell history

______________________________________________________________________

### `backups clean` dry-run preview

`pathkeeper backups clean --dry-run` — show exactly which files would be
pruned under the current retention config without deleting anything.

Why it could help:

- Users don't always understand how pruning works until they see it
- Makes it safe to experiment with different max_backups values
- Currently pruning happens silently as a side effect of backup

______________________________________________________________________

### Backup diff on restore

When `restore` is about to apply changes, always show the full diff before
the confirmation prompt — not just after `--dry-run`. Currently dry-run
shows the diff but the live path also shows it; this is about making the
pre-confirm diff clearer and always present even without `--dry-run`.

(This may already partially work — just flagging it as worth verifying and
making consistent across all mutating commands.)

______________________________________________________________________

### Configurable backup directory location

Add `general.backup_dir` to `config.toml` so users can store backups on a
network drive, a synced folder (OneDrive, Dropbox), or a separate partition.

Why it could help:

- Network-backed backups survive OS reinstall
- OneDrive/Dropbox sync gives automatic offsite redundancy at no extra cost
- Needed for the "restore on a new machine" story

______________________________________________________________________

### PATH entry search

`pathkeeper search <pattern>` — find entries matching a glob or substring,
across current PATH and optionally across all backups.

Why it could help:

- Useful when trying to find "where is Python on this machine?"
- Could show which backup(s) contained a now-missing entry
- Zero additional infrastructure — just filtered inspect output

______________________________________________________________________

## Potential next candidates

If only a few of these move forward soon, these seem especially strong:

1. `pathkeeper status --json` — unlocks shell prompt and CI integrations
1. `doctor --ci` exit codes — makes CI adoption trivial
1. Diff between two backups — high utility, low complexity
1. Lazy config singleton — two-line win, no trade-offs
1. Startup skip fast-path via sentinel file — biggest remaining startup win
1. Configurable backup directory — needed for "new machine restore" story
1. `pathkeeper export` for dotfiles — bridges two common workflows
