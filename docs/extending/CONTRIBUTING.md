# Contributing

Thanks for taking an interest in `pathkeeper`.

## Local setup

```bash
uv sync --python 3.14
```

## Development commands

```bash
make test
make typecheck
make check
```

You can also run them directly:

```bash
uv run pytest
uv run mypy pathkeeper tests
```

## Coding expectations

- keep changes typed and mypy-clean
- preserve the safety guarantees around backups and writes
- avoid touching content outside `pathkeeper`-managed PATH blocks on Unix
- add or update tests when behavior changes

## Documentation

The docs site is driven by `mkdocs.yml`, and Read the Docs installs dependencies from `docs/requirements.txt`.

When you add commands or change behavior, update the corresponding page under `docs/usage/`.
