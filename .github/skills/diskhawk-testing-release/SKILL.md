---
name: diskhawk-testing-release
description: "Use when testing, packaging, linting, verifying, or preparing a DiskHawk release, including CLI, TUI, shell integration, and acceptance criteria."
---

# DiskHawk testing and release

## Workflow

1. Review the SRS acceptance criteria and identify the exact behavior affected.
2. Run focused tests first, then the full suite:
   `python -m pytest`.
3. Run `ruff check .` and `ruff format --check .`.
4. Run coverage with `python -m pytest --cov`; keep core, config, and privacy
   coverage at or above the project target of 85%.
5. Verify an install/build from `pyproject.toml` and run the installed CLI's
   help/version smoke checks.
6. For shell changes, use a temporary home/startup file and a clean zsh/bash
   process; never modify a developer's real shell files in tests.
7. Mock Docker calls. Do not require a live daemon, network, `sudo`, or personal
   filesystem contents. If an explicit read-only Docker smoke test is run,
   disclose that the active context may be remote.
8. Report only checks actually run and distinguish unverified behavior.

## Release safety

Do not ship placeholders, sample output as live results, dead TUI actions,
unreported partial scans, or undocumented command flags. Confirm reports are
valid JSON and profile imports fail atomically for invalid data.
