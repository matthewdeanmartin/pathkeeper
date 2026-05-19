# Workflows

These workflows focus on how the current implementation is best used in practice.

## Baseline protection on a new machine

Create an immediate backup after you finish a clean setup:

```bash
uv run pathkeeper backup --note "baseline after setup"
```

Then install a schedule:

```bash
uv run pathkeeper schedule install --interval startup
```

## Investigating a broken PATH

When commands suddenly stop resolving:

```bash
uv run pathkeeper doctor
uv run pathkeeper inspect --only-invalid
```

If you already know you had a good state before:

```bash
uv run pathkeeper restore 2025-03-05T14-30-00 --dry-run
uv run pathkeeper restore 2025-03-05T14-30-00 --force
```

## Cleaning up PATH drift

If your PATH has accumulated stale entries and duplicates:

```bash
uv run pathkeeper dedupe --dry-run
uv run pathkeeper dedupe --force
```

Use `--keep last` when you want the newest duplicate to win instead of the oldest.

## Adding common tool directories

If a tool is installed but still not on PATH:

```bash
uv run pathkeeper populate --dry-run
uv run pathkeeper populate --force
```

You can narrow the scan to a category:

```bash
uv run pathkeeper populate --category "Programming Languages" --dry-run
```

## Making one targeted edit

Use `edit` when you know exactly what you want to change:

```bash
uv run pathkeeper edit --add "/opt/mytool/bin" --force
uv run pathkeeper edit --remove "/broken/path" --force
```

## Testing commands safely with `--var`

Use `--var NAME` to run the full command surface against a scratch variable instead of your real `PATH`. This lets you verify behavior, write tests, or experiment without any risk of modifying the live environment.

```bash
# Create a test variable with known entries
export PATHX="/usr/local/bin:/usr/bin:/opt/mytool/bin:/usr/bin"  # note the duplicate

# Inspect and diagnose
uv run pathkeeper --var PATHX inspect
uv run pathkeeper --var PATHX doctor

# Back it up
uv run pathkeeper --var PATHX backup --note "test baseline" --force

# Dedupe the duplicate without touching PATH
uv run pathkeeper --var PATHX dedupe --dry-run
uv run pathkeeper --var PATHX dedupe --force

# Edit an entry
uv run pathkeeper --var PATHX edit --add "/opt/newtool/bin" --force

# Compare backup to current state
uv run pathkeeper --var PATHX diff-current 1
```

The `--var` flag is supported by all read and write subcommands. On Windows, only the default `PATH` value accesses the registry; any other variable name uses the current process environment.
