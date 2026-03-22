# Installation

## Requirements

- Python 3.14
- `uv`

The repository also includes a `Makefile` for common development tasks.

## From a git checkout

```bash
git clone https://github.com/matthewdeanmartin/pathkeeper
cd pathkeeper
uv sync --python 3.14
```

You can then run:

```bash
uv run pathkeeper --version
uv run pathkeeper doctor
```

## Development shortcuts

```bash
make sync
make test
make typecheck
make check
```

## Documentation build

Read the Docs is configured to use `mkdocs.yml` and install documentation dependencies from `docs/requirements.txt`.

To build locally:

```bash
uv run --with-requirements docs/requirements.txt mkdocs build
```

To preview locally:

```bash
uv run --with-requirements docs/requirements.txt mkdocs serve
```
