# API

`pathkeeper` is primarily a CLI tool, but the package also contains reusable modules.

## Main modules

### `pathkeeper.cli`

Command parsing and top-level dispatch. This is the entry point behind the `pathkeeper` console command.

### `pathkeeper.config`

Application state directories, default config rendering, and config loading.

### `pathkeeper.models`

Shared dataclasses and enums such as `Scope`, `PathSnapshot`, `BackupRecord`, `DiagnosticReport`, and `CleanupResult`.

### `pathkeeper.core.backup`

Backup creation, loading, listing, resolution, and retention pruning.

### `pathkeeper.core.diagnostics`

PATH parsing, expansion, normalization, health analysis, and doctor recommendations.

### `pathkeeper.core.dedupe`

Duplicate and invalid-entry cleanup logic.

### `pathkeeper.core.diff`

Simple list-based PATH diff generation and rendering.

### `pathkeeper.core.edit`

Edit session state and list manipulation helpers for non-interactive editing.

### `pathkeeper.core.populate`

Catalog loading and discovery of tool directories missing from PATH.

### `pathkeeper.core.schedule`

Scheduling helpers for install, remove, and status across platforms.

### `pathkeeper.platform.*`

Platform adapters that read and write PATH using the correct OS-specific mechanism.

## Stability note

The CLI is the stable user-facing interface.

Direct Python imports should currently be treated as implementation-oriented extension points rather than a frozen public API contract.
