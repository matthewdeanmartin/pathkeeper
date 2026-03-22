# Extension points

`pathkeeper` is intentionally small and split into focused modules so it is easy to extend.

## Package layout

```text
pathkeeper/
├── cli.py
├── interactive.py
├── config.py
├── models.py
├── errors.py
├── core/
│   ├── backup.py
│   ├── dedupe.py
│   ├── diagnostics.py
│   ├── diff.py
│   ├── edit.py
│   ├── path_reader.py
│   ├── path_writer.py
│   ├── populate.py
│   └── schedule.py
└── platform/
    ├── windows.py
    ├── macos.py
    ├── linux.py
    └── unix_common.py
```

## Useful extension areas

### Add more populate patterns

Update `pathkeeper/catalog/known_tools.toml` to expand the built-in tool discovery catalog.

### Improve interactive flows

The interactive menu lives in `pathkeeper/interactive.py`. It is intentionally simple today and can be expanded into richer guided workflows.

### Add new diagnostics

The diagnostics engine is in `pathkeeper/core/diagnostics.py`. This is the right place to add new PATH health checks and recommendations.

### Evolve scheduling

The scheduling logic is in `pathkeeper/core/schedule.py`. Platform-specific changes there should stay focused on installing, removing, and checking recurring backup jobs.
