---
name: diskhawk-implementation
description: "Use when implementing or changing DiskHawk CLI, filesystem scanning, disk summaries, Docker inspection, shell integration, or Textual UI behavior in this repository."
---

# DiskHawk implementation

Use this skill for feature work in this repository. Read
`DiskHawk_SRS_Implementation_Plan.md` as the product contract before changing
behavior.

## Workflow

1. Inspect the existing implementation and tests; preserve unrelated changes.
2. Keep domain logic in `src/diskhawk/core/`, CLI adaptation in `commands` or
   `cli.py`, configuration in `config/`, and UI presentation in `tui/`.
3. Reuse shared services between CLI and TUI; do not implement a second scanner
   inside a widget.
4. Preserve read-only behavior. Do not add file deletion, Docker prune/stop,
   privilege escalation, network calls, telemetry, or AI interpretation.
5. Use subprocess argument arrays and timeouts. Never use `shell=True` or `eval`.
6. Add focused tests and update user documentation for every behavior change.
7. Run `python -m pytest`, `ruff check .`, and `ruff format --check .`.

## Product constraints

- Do not follow symlinks by default. Mark errors and depth-limited/cancelled
  results as partial.
- Report logical size and `st_blocks * 512` allocation estimates honestly; do
  not call either reclaimable space.
- `diskhawk info` must not scan directories or query Docker.
- Route only phrases listed in the phrase router. Unknown text is not shell code.
- Protect filesystem names, user paths, and report details at export boundaries.
