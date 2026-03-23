# pathkeeper brainstorm ideas

This document collects future ideas that could make `pathkeeper` more useful, safer, or easier to adopt. These are intentionally exploratory rather than committed requirements.

## Repair and recovery ideas

### PATH profiles

Let users save named profiles such as `work`, `gaming`, `minimal`, or `python-only`, then switch between them safely.

Why it could help:

- gives users a cleaner alternative to hand-editing PATH for different workflows
- makes rollback easier when tool installers add noisy entries
- opens the door to policy checks like “this profile may not modify system PATH”

### Quarantine bucket for removed entries

Instead of only deleting invalid or suspicious entries, move them into a quarantine list stored alongside the backup.

Why it could help:

- gives users confidence that cleanup is reversible
- makes it easier to review “what got removed and why”
- supports a future “restore one quarantined item” flow

### Repair from installed apps inventory

On Windows, inspect uninstall registry keys or common install metadata to find likely tool homes. On Unix, inspect package manager metadata such as Homebrew, apt, pacman, or asdf directories.

Why it could help:

- could find better repair candidates than raw filesystem search alone
- helps recover from cases where PATH was wiped or badly truncated
- improves explanations like “this looks like Python 3.14 from App Installer”

### Restore selected entries from a backup

Allow restoring only some entries from a snapshot instead of the entire scope.

Why it could help:

- useful when only one or two good entries were lost
- reduces risk compared with a full restore
- matches the real-world “put back just the missing toolchain” workflow

## Prevention ideas

### PATH guard / watch mode

Offer an optional background watcher that notices PATH changes and creates a backup before or immediately after mutation.

Why it could help:

- catches installer damage even when the user forgets to run a backup first
- could generate a clear “PATH changed at 14:32 by installer session” event trail
- pairs naturally with the existing scheduled backup story

### PATH budget and warnings

Track total PATH length against configurable budgets, not just hard OS limits.

Why it could help:

- gives earlier warning before the system reaches failure territory
- helps users make deliberate tradeoffs about large tool stacks
- could support recommendations such as dedupe, profile splitting, or shell shim usage

### Protected entries

Allow users to mark some entries as protected so cleanup or populate flows cannot remove or reorder them without an explicit override.

Why it could help:

- avoids accidental damage to business-critical internal tool paths
- helps teams standardize a small “must keep” set
- makes interactive repair safer for cautious users

### Safer installer compatibility mode

Add guidance and optional helper commands specifically for Windows `setx`/legacy truncation scenarios.

Why it could help:

- targets one of the most common PATH disasters
- could warn users before they copy a dangerous command
- gives the tool a strong practical identity around real PATH failures

## Explainability and diagnostics ideas

### Root-cause hints

Go beyond “invalid” and “duplicate” to suggest likely causes such as truncation, drive-letter loss, bad quoting, shell export mistakes, or removed software.

Why it could help:

- teaches users what happened instead of only showing symptoms
- makes interactive repair feel more trustworthy
- improves supportability when users share output in bug reports

### Health score

Compute a simple PATH health score with contributing factors.

Why it could help:

- gives users a fast way to gauge whether a repair improved things
- makes reports easier to scan in CI or scheduled checks
- could support future dashboards or badges

### “Why is this entry here?” trace

Explain where an entry came from when possible: system PATH, user PATH, pathkeeper-managed block, restored backup, populate action, or scheduled repair.

Why it could help:

- reduces mystery around merged PATH state
- helps users understand which scope to edit
- would be especially useful on Unix where effective PATH can be confusing

## Interactive UX ideas

### Guided startup triage

When the startup summary shows problems, offer a short triage menu such as:

- repair truncated entries
- remove invalid entries
- remove duplicates
- browse backups
- restore known-good snapshot

Why it could help:

- turns diagnostics into action quickly
- reduces the need to know command names
- matches the “my PATH is broken right now” mindset

### Undo stack across commands

Keep a short session-local undo history for mutating actions, not just within the editor.

Why it could help:

- makes experimentation less scary
- smooths multi-step cleanup sessions
- complements pre-operation backups with faster local reversibility

### Dry-run plus command recipe

After previewing an action interactively, print the equivalent direct CLI command.

Why it could help:

- helps users learn automation paths
- makes support and documentation easier
- bridges interactive and scripted usage cleanly

## Team and fleet ideas

### Shared team policy file

Support a checked-in policy file that defines required entries, forbidden entries, preferred ordering, and allowed scopes.

Why it could help:

- turns pathkeeper into a team hygiene tool rather than only a personal rescue tool
- could help developer onboarding
- enables consistent CI or workstation checks

### Machine bootstrap audit

Compare the current machine against a desired PATH baseline and print a setup gap report.

Why it could help:

- useful for new laptops and rebuilds
- could pair well with populate and restore
- provides value even when nothing is broken

### Export/import machine repair bundle

Export backups, config, and recent diagnostics into a portable bundle that can be imported elsewhere.

Why it could help:

- useful for support scenarios and migrations
- makes it easier to help someone recover a broken machine remotely
- provides a cleaner story than manually copying JSON files

## Shell integration ideas

### Command-not-found helper suggestions

When a tool is missing from PATH but present on disk, offer a suggested `pathkeeper` repair command.

Why it could help:

- turns user pain into a discoverable recovery path
- helps adoption by meeting users in the shell where the failure occurs
- could be lightweight if implemented as optional shell glue

### Shell-specific doctor hints

Tailor diagnostics and next steps to PowerShell, CMD, bash, zsh, or fish.

Why it could help:

- avoids generic advice when shell behavior differs
- improves trust in Unix flows
- makes docs and help output feel more polished

## Potential next candidates

If only a few of these move forward soon, these seem especially strong:

1. guided startup triage
1. restore selected entries from a backup
1. repair from installed apps inventory
1. protected entries
1. dry-run plus command recipe
