# Contributing

## Setup

Requires Python 3.12+, `uv`, and `make`.

```bash
make sync                    # uv sync
uv run pre-commit install    # install the pre-commit hook (once)
uv run pathkeeper            # smoke test
```

The pre-commit hook runs `make check` before every commit — the same gate CI runs.

## Architecture

The codebase has four layers:

- **`pathkeeper/platform/`** — OS adapters (`WindowsPlatform`, `UnixCommonPlatform`, etc.) that read and write PATH from the registry (Windows) or rc files (Unix). All platform reads are cached per-instance; the adapter is created fresh per command invocation, so the cache is intentionally not invalidated.
- **`pathkeeper/core/`** — pure logic modules (`backup`, `dedupe`, `diagnostics`, `edit`, `populate`, `repair_truncated`, `schedule`). Each module depends on the platform layer only through `PathSnapshot` and `PathWriter` — it never calls the adapter directly.
- **`pathkeeper/services.py`** — orchestration helpers shared between CLI and GUI. If you find yourself duplicating snapshot-loading or adapter-construction logic in `cli.py` or `gui/`, it belongs here instead.
- **`pathkeeper/cli.py`** and **`pathkeeper/gui/`** — entry points only; they delegate to `services.py` and core modules.

Key data types live in `models.py`:

- `PathSnapshot` — a frozen point-in-time view of system and user PATH (both parsed list and raw string)
- `BackupRecord` — a snapshot plus metadata (timestamp, tag, note, hostname)
- `Scope` — `system` / `user` / `all`; controls which registry keys or rc-file blocks are touched

Backups are JSON files in `~/.pathkeeper/backups/`. The raw PATH string is preserved alongside the parsed list so restore can round-trip values without re-joining and re-splitting.

On Unix, pathkeeper only rewrites content inside its own marker block in rc files — it does not touch anything outside that block.

On Windows, writes use `REG_EXPAND_SZ` and broadcast `WM_SETTINGCHANGE` so the new PATH is visible to subsequently opened shells without a logoff.

## Quality checks

`make check` is the gate that runs on every push. It runs:

```bash
make check         # format-check + lint-check + security + test + typecheck + metadata-check + version-check
```

Run it before pushing. If you only changed one area, the focused targets are faster:

```bash
make test          # pytest
make typecheck     # mypy (strict)
make lint-check    # ruff + pylint
make format-check  # black + isort + yamlfix
make security      # bandit
```

Fix formatting with:

```bash
make format        # formats then checks (isort + black + ruff --fix + yamlfix + mdformat)
```

## Additional checks

These are not in `make check` but are worth running when touching the relevant areas:

```bash
make shellcheck    # actionlint + shellcheck on all workflow files
make makefile-lint # checkmake on Makefile
make spell         # codespell
make docs          # pylint docstring rules
make gha-lint      # actionlint on .github/workflows/
make prepublish    # full check + dev-status + wheel content validation
```

Alternative type checkers (used to cross-check mypy findings, not required to pass):

```bash
make typecheck-ty
make typecheck-basedpyright
```

## Testing

Tests are in `tests/`. pytest runs with `-m 'not slow'` by default, which skips `@pytest.mark.slow` benchmarks.

```bash
make test          # fast tests only
make bench         # startup benchmarks (slow)
```

The test suite uses `hypothesis` for property-based tests. If hypothesis finds a failure it will shrink the input and save it in `.hypothesis/` — commit that directory if it captures a real edge case.

## Platform considerations

The Windows path-write path (`platform/windows.py`) uses `ctypes.windll`, which only exists on Windows. The `# type: ignore[attr-defined]` comments in that file are intentional and required — `mypy.overrides` for that module has `warn_unused_ignores = false` for exactly this reason. Do not remove them.

System PATH writes on Windows require elevation. The code raises `PermissionDeniedError` rather than silently falling back. The interactive flow offers a user-scope fallback; CLI callers should not swallow that error.

If you add a new mutating operation, follow the existing pattern: take a safety backup before writing (`restore.pre_backup = true` in config), accept a `--dry-run` flag, and accept a `--scope` argument where it makes sense.

## Adding to the tool catalog

`pathkeeper/catalog/known_tools.toml` is the list of directories `pathkeeper populate` scans for. Each entry has a `name`, `category`, `os` (or `"all"`), and a list of glob `patterns`. On first run the file is copied to `~/.pathkeeper/known_tools.toml` where users can extend it locally. The `extra_catalog` config key points to an additional file that is merged in.

## Metadata and versioning

```bash
make metadata      # regenerates __about__.py from pyproject.toml
make metadata-check  # verifies __about__.py is in sync (runs in CI)
make version-check # verifies version format
```

`__about__.py` is generated — do not edit it by hand. Run `make metadata` after bumping the version in `pyproject.toml`.

## CI

Four workflows:

| Workflow | Trigger | What it does |
|---|---|---|
| `build.yml` | push / PR | `make check` on Python 3.14 |
| `tox.yml` | push / PR | pytest + mypy across Python 3.13–3.14, Linux + Windows |
| `lint.yml` | push / PR | actionlint + shellcheck on workflows, checkmake on Makefile |
| `zizmor.yml` | push/PR to `.github/**` | GHA security audit, uploads SARIF |
| `publish_to_pypi.yml` | manual dispatch | `make check` + build + PyPI publish |

All action references are pinned to SHA hashes. Use `make gha-update` (requires `gh auth login` and `pinact`) to update them.
