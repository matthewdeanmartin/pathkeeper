# pathkeeper — Ideas: Unix & Cross-Platform

Ideas for improving pathkeeper on macOS and Linux, and for making the
cross-platform experience more consistent.

______________________________________________________________________

## Unix shell integration ideas

### Effective PATH vs. persistent PATH reconciliation

On Unix, `pathkeeper` reads the effective `$PATH` from the environment. But
the effective PATH is assembled at shell startup from multiple sources: system
files, user profile, `.bashrc`, `.zshrc`, `~/.profile`, conda/pyenv hooks, etc.

A `reconcile` command (or a section of `doctor`) could:

- Show which directories in the effective `$PATH` are NOT represented in any
  known shell config file
- Flag directories that ARE in a config file but not currently effective
- Suggest which file to edit for a given entry

Why it could help:

- Unix PATH debugging is notoriously opaque — "why does this work in a login
  shell but not in a script?"
- Gives users a map between effective PATH and its sources
- Would make pathkeeper genuinely useful to experienced Unix users, not just Windows newcomers

______________________________________________________________________

### macOS `/etc/paths.d/` and `path_helper` awareness

macOS assembles system PATH using `path_helper(8)` which reads `/etc/paths`
and `/etc/paths.d/*.txt`. Currently pathkeeper reads the effective `$PATH`
but doesn't know which entries came from `path_helper`.

Enhancements:

- Parse `/etc/paths` and `/etc/paths.d/` directly on macOS to identify
  system-controlled entries
- Flag entries that are in `path_helper` sources but not in the effective PATH
  (could indicate a shell that bypassed `path_helper`)
- Warn when entries from `path_helper` are shadowed by user entries earlier
  in `$PATH`
- For the backup: store both effective PATH and `path_helper` source entries

Why it could help:

- macOS PATH assembly is confusing even to experienced developers
- `/etc/paths.d/` packages (Homebrew, Xcode CLI tools) are often the source
  of confusion
- Gives macOS users a first-class experience rather than a fallback

______________________________________________________________________

### Homebrew prefix detection and validation

Detect the Homebrew prefix (`/opt/homebrew` on Apple Silicon, `/usr/local`
on Intel) and validate that the expected Homebrew directories are present and
in the right order relative to system dirs.

Specific checks:

- `$(brew --prefix)/bin` should appear before `/usr/bin` for GNU tools to work
- `$(brew --prefix)/sbin` presence
- `$(brew --prefix)/opt/*/bin` for keg-only formulae that need explicit PATH addition

Why it could help:

- Homebrew ordering issues cause subtle breakage (wrong `python`, `gcc`, `git`)
- Common on Apple Silicon where ARM and Intel Homebrew can coexist
- Would give pathkeeper a strong identity in the macOS developer community

______________________________________________________________________

### asdf / mise / rtx version manager integration

`asdf`, `mise` (formerly `rtx`), and similar version managers inject shim
directories into PATH. Pathkeeper should:

- Detect shim directories by pattern (`~/.asdf/shims`, `~/.local/share/mise/shims`)
- Warn when shims are in a surprising position relative to system tools
- Flag when a shim directory is present in PATH but the version manager doesn't
  appear to be installed
- Explain that removing a shim directory may not be what the user wants

Why it could help:

- Version manager users are a large segment of the developer audience
- Shim directories often cause confusion in diagnostics ("this dir has no real binaries")
- Better explanations reduce false-positive "invalid entry" noise

______________________________________________________________________

### pyenv / rbenv / nvm / fnm bootstrap check

These version managers require their init hooks to run before PATH is fully
configured. If `pathkeeper` detects a version manager directory on PATH but
the corresponding init hook doesn't appear to be sourced, warn the user.

Example: `~/.pyenv/shims` is on PATH but `pyenv init -` is not in `~/.bashrc`.

Why it could help:

- A very common source of "the version manager is installed but tools don't work"
- Pathkeeper already reads the PATH; checking for known manager patterns is cheap
- Would make pathkeeper useful even to users who aren't actively experiencing a disaster

______________________________________________________________________

### fish shell support

`fish` does not use `.bashrc` or `.zshrc`. Its PATH is managed via
`fish_add_path` (persistent) or `set -x PATH` (session-only), stored in
`~/.config/fish/fish_variables`.

Improvements:

- `pathkeeper shell-startup --shell fish` should inject a `pathkeeper backup`
  call into `~/.config/fish/config.fish` using the correct fish syntax
- The doctor should mention fish if it's detected as the login shell
- `pathkeeper populate` should suggest `fish_add_path` rather than `export PATH=`
  in its output when fish is the shell

Why it could help:

- fish is increasingly popular and has quite different PATH management
- The current shell-startup doesn't support it at all
- fish users who try pathkeeper today get a confusing experience

______________________________________________________________________

## Cross-platform ideas

### Portable backup format version 2

The current backup format stores raw PATH strings (semicolons on Windows,
colons on Unix). A version 2 format could:

- Store entries as a structured array (already done) AND record the delimiter
- Store environment variable references in a cross-platform notation:
  `{HOME}` instead of `%USERPROFILE%` or `$HOME`
- Include a `platform_hints` object with OS-specific metadata

Why it could help:

- Enables partial cross-platform restore (e.g. restoring tool names from a
  Windows backup onto a Linux machine)
- Makes export/import to dotfiles repos more portable
- Future-proofs the format without breaking v1 compatibility

______________________________________________________________________

### WSL (Windows Subsystem for Linux) PATH awareness

WSL automatically appends Windows PATH entries to the Linux PATH. This
causes:

- Very long effective PATH inside WSL
- Windows tool paths showing up as "missing" in the Linux inspector
- Confusion about which entries are Linux-native vs Windows-injected

Enhancements:

- Detect when running inside WSL via `/proc/version` or `WSL_DISTRO_NAME`
- Filter out Windows-injected entries from the Linux inspector view
- Offer a WSL-specific summary: "12 native entries, 38 Windows-injected entries"
- Respect `WSLENV` for cross-environment PATH exports

Why it could help:

- WSL is a major usage context for Windows developers
- The current inspector would flag many Windows paths as invalid inside WSL
- A WSL-aware mode would make pathkeeper usable in both Windows and WSL contexts

______________________________________________________________________

### NixOS / Nix package manager awareness

Nix manages binaries through a store (`/nix/store/...`) and symlinks.
The PATH entries it creates are long, content-addressed, and look broken to
normal existence checks.

Specific handling:

- Detect Nix store paths by pattern (`/nix/store/*`)
- Skip existence checks for Nix store paths (they are content-addressed and valid)
- Warn when `~/.nix-profile/bin` is missing from PATH if Nix is installed
- Recognize `nix-env` and `nix profile` as PATH-modifying operations

Why it could help:

- NixOS users who try pathkeeper today get many false "invalid" warnings
- Nix is increasingly used on macOS and Linux as a package manager
- A single special case eliminates a whole class of noise

______________________________________________________________________

### Conda environment PATH injection awareness

Conda prepends its environment's `bin` directory to PATH when an environment
is activated. This means:

- Effective PATH differs dramatically between "conda activated" and "base" shell
- Backups taken in an activated environment don't represent the base PATH
- Restoring such a backup into a non-activated shell would inject garbage

Enhancements:

- Detect `CONDA_PREFIX` / `CONDA_DEFAULT_ENV` and warn in backup output:
  "Conda environment 'myenv' is active — backup reflects activated PATH"
- Offer `--base` flag to strip conda-injected entries before backup
- Tag backups with conda environment metadata

Why it could help:

- Data scientists are a large potential audience for pathkeeper
- Conda PATH corruption (especially from failed environment deactivation) is common
- The warning alone would prevent many surprising restores

______________________________________________________________________

## Potential next candidates

If only a few of these move forward soon, these seem especially strong:

1. fish shell support for `shell-startup` — unblocks a real user segment today
1. WSL PATH awareness — many Windows devs run in both contexts
1. Homebrew prefix validation — strong macOS developer identity
1. Conda environment detection — important safety check for a large audience
1. Effective PATH vs. persistent PATH reconciliation — the hardest but most
   valuable Unix feature
