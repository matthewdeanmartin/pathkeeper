# Quick Start

This is the shortest useful path to getting value from `pathkeeper`.

## 1. Create a backup

```bash
uv run pathkeeper backup --note "clean machine baseline"
```

This writes a JSON backup into `~/.pathkeeper/backups/`.

## 2. Check PATH health

```bash
uv run pathkeeper doctor
```

Use `doctor` when you want a summary and recommended next steps. Use `inspect` when you want the full entry listing.

## 3. Preview a restore before writing

```bash
uv run pathkeeper restore 2025-03-05T14-30-00 --dry-run
```

You can pass either a backup filename or a timestamp prefix.

## 4. Clean up duplicates and dead entries

```bash
uv run pathkeeper dedupe --dry-run
uv run pathkeeper dedupe --force
```

The first command previews the cleanup. The second applies it without an interactive confirmation prompt.

## 5. Find an executable

```bash
uv run pathkeeper locate python
```

Use `locate` when you know a tool is installed but you're not sure where it is or if it's on your PATH.

## 6. Start from the menu

```bash
uv run pathkeeper
```

Running with no subcommand opens the interactive menu.
