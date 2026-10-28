# Privacy and report behavior

DiskHawk runs locally and makes no network requests. It has no telemetry,
account, server, or AI integration. The app does not read environment-variable
values, `.env` files, keychains, secrets, file content, or Docker container
environment variables.

## Default reports

`diskhawk report` writes a local text report. JSON is selected with
`--format json`. Reports contain a schema/app version, UTC timestamp, operating
system and Python metadata, filesystem capacity/used/available values, and
sanitized active preferences. Home-directory paths are shortened to `~`.
Filenames and full recursive file inventories are excluded by default. Docker
details are not queried unless `--docker` is explicitly supplied.

The JSON report schema (version 1) has stable top-level fields:
`schema_version`, `app`, `created_at`, `platform`, `filesystems`, `scan`,
`docker`, `warnings`, `warning_count`, `error_count`, and `settings`. Each
filesystem uses `mount_point`, `total_bytes`, `used_bytes`, `available_bytes`,
and `usage_percent`; byte values are integers. `docker` reports whether the CLI
exists without querying a daemon by default (`state: not_queried`). `scan` is
`null` unless `--scan-path` is specified; scan filenames are included only with
explicit detailed opt-in. Reports include only the count of configured exclude
patterns and omit absolute report-directory preferences.

Reports are not uploaded or transmitted. The destination is local. Existing
output is not silently overwritten.

## Explicit detailed-name opt-in

`--scan-path PATH` explicitly scans a directory to add aggregate statistics.
`--include-details` requires `--scan-path` and adds relative names from the top
scan entries only; it does not include file contents. In an interactive
terminal DiskHawk asks for confirmation. In non-interactive use,
`--yes-include-details` is also required.
Treat a detailed report as potentially identifying and review it before sharing.

## Configuration profiles

Profiles export only documented DiskHawk preferences. They do not contain
credentials or environment values. Import validates all keys/types/limits,
previews changes, and writes the new configuration atomically after confirmation.
Imported values are data, never executable code.

## Scan semantics

Scan results contain relative file and directory names in the terminal output.
The scanner does not follow symlinks or change scanned items. Logical and
allocated-size estimates can differ from physical disk space reclaimed because
of APFS snapshots, clones, compression, hard links, open files, and filesystem
metadata.
