```
Dedupe
  --------

System diff:
No changes.

User diff:
No changes.
Created backup: C:\Users\matth\.pathkeeper\backups\2026-03-23T20-37-22_pre-dedupe.json
Apply dedupe changes? [y/N]: N
  Error: User cancelled.
```

Why did it offer to apply changes adn make a useless backup on a No Changes/No Changes dedupe? It shouldn't backup, nor
offer to dedupe if there is no deduplication to be done, it should just report it out and return to menu.

```.bashrc
pathkeeper backup --quiet --tag auto  # pathkeeper backup (added by pathkeeper shell-startup)
```

I open a new shell and I get

"bash: pathkeeper: command not found"

I wouldn't expect this to work without the venv being properly activated and there is no venv activation happening there.

This would only work if installed via pipx. Not sure about uv or other pipx clones.

______________________________________________________________________

Again, if I run inspect, it says there are dupes, but on dedupe, it says, nope, no dupes.

Entries: 58 valid: 58 invalid: 0 duplicates: 24 empty: 0
Warning: PATH exceeds the legacy setx limit of 2047 characters.

[1] Inspect Review PATH entries and their health
[2] Doctor Diagnose problems and suggest repairs
[3] Create backup Save the current PATH snapshot
[4] List backups Browse recent backups and hashes
[5] Show backup Inspect one backup in detail
[6] Restore Restore the most recent backup
[7] Dedupe Remove duplicates and broken entries
[8] Populate Discover common tool directories
[9] Edit Stage PATH changes in an editor
[10] Repair truncated Repair entries missing leading path segments
[11] Schedule status Check or install automatic backups
[12] Shell startup Inject backup hook into shell startup file
[q] Quit

> 7

## Dedupe

System diff:
No changes.

## User diff: No changes. WARNING: Skipping backup because the current PATH matches the latest saved backup. Apply dedupe changes? \[y/N\]:

I think this has something to do with me not normally running in an elevated shell.
I think if there is an entry in the user section and an entry in the system section, then the user section entry can be removed, right?
But it acts like all the dupes are solely inside system and they get filtered out.
