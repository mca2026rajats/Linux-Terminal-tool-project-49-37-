# Contributing

## Development setup

Use Python 3.12 or newer and an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Validation

```bash
python -m pytest
ruff check .
ruff format --check .
python -m pytest --cov
```

Tests must use temporary directories and mocks. Do not modify real shell startup
files, inspect personal disk contents, require `sudo`, require network access,
or depend on a live Docker daemon. Optional Docker integration checks must be
read-only and explicitly skipped when unavailable.

Keep CLI and TUI behavior on shared core services. Preserve the read-only,
privacy-safe product boundaries, document user-visible behavior, and avoid
claiming a feature that tests do not verify.
