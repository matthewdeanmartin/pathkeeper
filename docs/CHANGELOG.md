# Change Log

## 0.1.0

Initial implementation of `pathkeeper`.

Highlights:

- typed Python 3.14 project managed with `uv`
- CLI commands for `inspect`, `doctor`, `backup`, `restore`, `dedupe`, `populate`, `edit`, and `schedule`
- platform adapters for Windows, macOS, and Linux
- local backup store in `~/.pathkeeper/backups/`
- config and known-tools catalog bootstrapping
- test coverage for backups, diagnostics, dedupe behavior, CLI flows, and Unix PATH file management
- MkDocs and Read the Docs documentation scaffold
