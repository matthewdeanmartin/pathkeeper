# pathkeeper — Ideas: Windows Deep Integration

These ideas are specific to Windows, where PATH management is most painful
and where pathkeeper currently has the most complete implementation.

______________________________________________________________________

## Windows-specific pain points worth targeting

### `setx` truncation recovery assistant

`setx` silently truncates PATH to 1024 characters — one of the most common
PATH disasters on Windows. A dedicated `pathkeeper repair-setx` (or an
improved warning in `repair-truncated`) could:

1. Detect the telltale sign: current PATH is exactly 1023 or 1024 chars
1. Explain what happened and why (the `setx` 1024-byte limit)
1. Offer to restore from the most recent pre-truncation backup automatically
1. Warn if no backup exists and offer to try filesystem-based repair instead

Why it could help:

- `setx` truncation is the #1 most-reported PATH disaster on Stack Overflow
- Users who hit it often don't know what caused it
- Pathkeeper is already the right tool — this just makes the entry point obvious

______________________________________________________________________

### Windows registry watcher (optional daemon)

Use the `winreg.RegNotifyChangeKeyValue` API to watch for PATH changes in the
registry without polling, then fire a backup immediately when a change lands.

Why it could help:

- Catches installer damage the moment it happens, not at next shell startup
- Requires no admin rights for the user PATH key
- Could run as a tray icon process or a background Windows service
- Pairs with the event log idea: "PATH changed at 14:32, backup created"

Risks / considerations:

- Background process has UX implications (install, uninstall, visibility)
- Should be strictly opt-in
- Needs to handle the case where pathkeeper itself is the writer

______________________________________________________________________

### `%VAR%` expansion audit

The current inspector flags unexpanded `%VARIABLES%` as a warning. A deeper
audit would:

- Expand every variable and check if it resolves
- Detect variables that are set at system level but not user level (or vice versa)
- Flag entries that expand differently in User vs System context
- Suggest `pathkeeper fix-vars` to either expand in place or leave as-is

Why it could help:

- Unexpanded vars are a frequent source of "works for admin, breaks for user"
- Expansion failures are currently shown as missing dirs, masking the real cause
- Gives users actionable advice rather than just a red marker

______________________________________________________________________

### Windows Package Manager (winget) path discovery

Extend the catalog with paths for winget-installed tools:

- `%LOCALAPPDATA%\Microsoft\WinGet\Packages\**\bin`
- `%LOCALAPPDATA%\Microsoft\WinGet\Links`

Also: query `winget list --source winget` if winget is available to infer
which of the catalog patterns are actually installed, reducing false-positive
matches in `populate`.

Why it could help:

- Winget is now the dominant Windows package manager on modern installs
- Many users don't know their winget tools need PATH entries
- Querying the installed list makes populate smarter

______________________________________________________________________

### Windows App Execution Aliases detection

`%LOCALAPPDATA%\Microsoft\WindowsApps` contains execution aliases for
Microsoft Store apps. Currently this is in the catalog, but the inspector
could specifically:

- Detect when this directory is present multiple times (common after upgrades)
- Warn when aliases shadow real executables earlier on PATH
- Explain what execution aliases are when flagging them

Why it could help:

- WindowsApps is a unique and confusing directory
- It often appears in both system and user PATH after Store app installs
- Users frequently don't understand why `python` resolves to the Store stub

______________________________________________________________________

### Windows PATH length approaching-limit early warning

The OS limit for environment variable expansion is 32,767 characters
(`MAX_ENV_VALUE_LENGTH`), but the practical registry limit for `PATH` stored
as `REG_EXPAND_SZ` is 2047 characters in some older Windows contexts.

Enhancements:

- Track system + user combined length after expansion (not just raw)
- Warn at 80%, error at 95% of the relevant limit
- Suggest specific entries to remove or paths to shorten
- `pathkeeper doctor` could include a PATH length gauge bar

Why it could help:

- Length warnings before hitting the limit are far better than silent failures
- The actual effective limit varies by context and version — users need guidance
- Pairs well with the dedup and populate flows

______________________________________________________________________

### ConEmu / Windows Terminal profile path suggestions

Detect when ConEmu, Windows Terminal, or other terminal emulators add their
own directories to PATH and offer to move them to a predictable position.

Why it could help:

- Terminal emulators occasionally inject directories that shadow system tools
- Position matters: a terminal's injected dirs shouldn't come before system dirs
- Could be a simple check in `doctor`: "terminal emulator directory detected out of order"

______________________________________________________________________

### PowerShell profile PATH management

`pathkeeper` currently injects a backup line into the PowerShell profile.
A richer integration could:

- Read what the PowerShell profile currently adds to `$env:PATH`
- Offer to migrate those manual `$env:PATH += ...` lines into the registry
- Warn when PowerShell profile PATH additions shadow registry PATH entries

Why it could help:

- Many Windows users manually extend PATH in their PS profile, leading to
  dual-layer PATH complexity
- Migrating to the registry makes changes permanent and visible to all processes
- Reduces confusion about "why does it work in PowerShell but not in cmd?"

______________________________________________________________________

### Windows Credential Guard / sandbox detection

Detect when running inside a Windows Sandbox, Hyper-V guest, or Docker container
and suppress or adapt registry-based operations that won't work or won't persist.

Why it could help:

- Sandbox environments have different PATH semantics
- Writing to the registry in a Sandbox is pointless (changes don't persist)
- A clear "running in sandbox mode — backup will be session-only" message
  is better than silent incorrect behavior

______________________________________________________________________

## Potential next candidates

If only a few of these move forward soon, these seem especially strong:

1. `setx` truncation recovery assistant — targets the #1 Windows PATH disaster
1. `%VAR%` expansion audit — turns a warning into an explanation with a fix
1. winget path discovery — keeps the catalog current with modern Windows usage
1. PATH length approaching-limit early warning — proactive rather than reactive
1. Windows App Execution Aliases detection — addresses a common confusion point
