# Commands

All commands are local. Exit codes: `0` success, `1` operational/internal
failure, `2` invalid arguments or unsupported phrase, `3` partial scan, and `4`
requested optional integration unavailable.

| Command | Purpose |
|---|---|
| `diskhawk` | Show concise command help. |
| `diskhawk info` | Show the pixel-art capacity dashboard and approximately one-second physical read/write throughput sample without walking directories. |
| `diskhawk info --all` | List curated mounted filesystems; pseudo-filesystems are filtered. |
| `diskhawk info --include-network` | Include network mounts in the curated filesystem list. |
| `diskhawk info --threshold 85` | Override the warning threshold (1–100%). |
| `diskhawk info --json` | Emit filesystem raw byte values and stable JSON keys without waiting for live activity sampling. |
| `diskhawk scan [PATH]` | Scan a directory (default `.`), without following symlinks. |
| `diskhawk scan PATH --top 20` | Return at most 20 largest individual files/directories. |
| `diskhawk scan PATH --min-size 100MB` | Filter displayed entries; decimal `MB` and binary `MiB` units are accepted. |
| `diskhawk scan PATH --max-depth 4` | Limit traversal depth; report marks totals partial/depth-limited. |
| `diskhawk scan PATH --exclude '*.cache'` | Repeatable basename or relative-path glob exclusion. |
| `diskhawk scan PATH --json` | Emit scan metadata and raw byte counts as JSON. |
| `diskhawk scan / --allow-root` | Explicitly permit a root scan; interactive use asks for confirmation. |
| `diskhawk docker` | Query read-only Docker system disk usage and active context. |
| `diskhawk report` | Write a sanitized text report in the current directory. |
| `diskhawk report --format json --output PATH` | Save a versioned JSON report. Existing files are not overwritten without confirmation or `--force`. |
| `diskhawk report --scan-path PATH` | Include aggregate scan statistics for an explicitly selected directory. |
| `diskhawk report --scan-path PATH --include-details` | Opt into relative top-entry names; non-interactive use also requires `--yes-include-details`. |
| `diskhawk report --docker` | Explicitly include Docker summary in the report. |
| `diskhawk profile show` | Show active non-secret configuration. |
| `diskhawk profile export [PATH]` | Export a validated JSON configuration profile. |
| `diskhawk profile import PATH` | Preview validated setting changes and confirm before applying. Use `--yes` for non-interactive confirmation. |
| `diskhawk ask TEXT...` | Route one of the supported deterministic phrases. |
| `diskhawk ui` | Launch the Textual interface. |
| `diskhawk shell install zsh\|bash` | Back up and add an opt-in phrase integration after conflict checks. |
| `diskhawk shell uninstall zsh\|bash` | Back up and remove only the marked integration block. |
| `diskhawk version` | Print version. |

Supported `ask` phrases:

- `give me disk info`
- `show disk info`
- `disk info`
- `check disk space`
- `how much disk space is left`
- `scan current folder`
- `find large files`
- `docker disk usage`

Unknown phrases are rejected; they are never executed as shell commands.

## Output interpretation

Human-readable units are binary (`KiB`, `MiB`, `GiB`, `TiB`); JSON values are
integer bytes. `available` comes from the operating system and can differ from
total minus used due to reserved space. Directory sizes are logical totals plus
an allocated-size estimate where `st_blocks` is available. Neither value
represents guaranteed reclaimable space.

`--exclude` matches either a relative path from the scan root or the entry's
basename using standard glob matching. Hidden files and common build folders
are included unless explicitly excluded.

The exact field set for JSON reports is versioned by `schema_version`; scan JSON
is a CLI result, not a persisted report schema.
