## Notes

- Backups preserve raw PATH strings so restore can round-trip values safely.
- `pathkeeper backup` skips creating a new backup when the latest saved snapshot has identical PATH content unless you
  pass `--force`.
- On Unix, `pathkeeper` only rewrites PATH content inside its managed marker block in user rc files.

### Windows

- In the interactive menu, `Dedupe` now offers a user-scope fallback when system PATH changes need elevation on Windows.
- If startup-task installation needs elevation, the interactive schedule flow offers a per-user logon task
  fallback.
- If Windows denies both the startup task and the logon-task fallback, the interactive schedule flow now explains the
  next step instead of exiting with a raw permission error.
- Registry writes use `REG_EXPAND_SZ` and broadcast an environment change notification.
