# DiskHawk — Software Requirements Specification & Implementation Plan

**Document status:** Build specification  
**Product:** DiskHawk  
**Version target:** 1.0.0 MVP  
**Primary platform:** macOS (Apple Silicon and Intel)  
**Implementation language:** Python  
**Audience:** An AI coding agent implementing the complete product end-to-end

---

## 1. Build Objective

Build **DiskHawk**, a lightweight, local-first terminal utility that explains disk usage on a Mac, finds large files and directories, reports Docker disk usage when Docker is available, and creates safe, shareable diagnostic reports and configuration profiles.

DiskHawk must provide both:

1. **Normal CLI commands** for fast, scriptable use.
2. **An interactive terminal UI (TUI)** with keyboard navigation and mouse support.

A core product requirement is that, after optional shell integration is installed, the user can type this exact phrase into a supported interactive shell:

```text
give me disk info
```

The phrase must display DiskHawk's disk summary. It must not require an AI service, network connection, account, or API key. Phrase recognition must be deterministic and local.

The project must be delivered as a working, installable, tested application—not just a scaffold or a collection of example files. Implement the requirements in this document together. Do not leave TODOs, placeholder handlers, fake output, or features that appear implemented but do not work.

## 2. Product Principles

- **Lightweight:** no server, daemon, database, cloud backend, AI API, or GUI framework.
- **Local-first:** disk inspection and report generation happen locally.
- **Read-only by default:** DiskHawk may inspect files and Docker usage, but must never delete files, prune Docker resources, stop containers, or terminate processes in v1.0.
- **Safe:** do not follow symlinks during directory scans by default; handle permissions and files disappearing during a scan without crashing.
- **Honest reporting:** distinguish actual filesystem capacity from estimated directory sizes. Never present an estimate as guaranteed reclaimable disk space.
- **Shareable by design:** reports and profiles must not include secret values. Share reports with minimal personal path information by default.
- **No hidden network activity:** the application must not make network requests. Docker commands are local CLI calls and may interact with the Docker context the user has configured; explain this behavior.
- **Shell-friendly:** ordinary commands must work in scripts and pipes. Color and progress UI must turn off or adapt when output is not an interactive terminal.
- **Complete first release:** implement, test, document, and package all P0 requirements before calling v1.0 complete.

## 3. Scope

### 3.1 In scope for v1.0

1. Disk summary for the startup volume, home directory, and current working directory's mounted filesystem.
2. Optional listing of other mounted filesystems and external volumes.
3. Recursive directory analysis with top largest files and directories.
4. Read-only Docker disk usage inspection, when Docker CLI and a reachable daemon are available.
5. Interactive TUI with search/filter, sorting, detail views, refresh, export, keyboard shortcuts, mouse selection, and scrolling.
6. Natural-language phrase matching for a small, documented set of disk-related phrases.
7. Optional shell integration so `give me disk info` works in macOS zsh; bash support should also be implemented if it can be done without compromising safety or reliability.
8. JSON and human-readable diagnostic reports, sanitized by default.
9. Export/import of portable DiskHawk configuration profiles, with schema validation.
10. Configuration file, error handling, tests, packaging, installation instructions, and troubleshooting documentation.

### 3.2 Explicitly out of scope for v1.0

- Deleting files, emptying Trash, running cleanup actions, or promising a specific amount of reclaimable space.
- Running `docker system prune`, deleting images/volumes, stopping containers, or changing Docker configuration.
- Process killing, port management, CPU/RAM monitoring, or system optimization.
- Cloud upload, accounts, telemetry, analytics, remote agents, or AI-based natural-language interpretation.
- A graphical desktop app or web dashboard.
- Reading `.env` files or exporting environment variable values. “Environment sharing” refers only to DiskHawk's safe settings profiles and sanitized reports.
- Automatically installing Docker or changing system permissions.

## 4. Technology Stack

Use the simplest stack that satisfies the product requirements.

| Component | Technology | Purpose |
|---|---|---|
| Language | Python 3.12 or newer | Core application and filesystem traversal |
| CLI framework | Typer | Commands, arguments, options, and help output |
| Terminal output | Rich | Tables, panels, progress, formatting, color theme |
| Interactive TUI | Textual | Keyboard/mouse interaction, tables, screens, dialogs |
| OS/path config | `pathlib`, `os`, `shutil`, `subprocess`, `platformdirs` | Filesystem and platform integration |
| Disk/mount inspection | Python standard library plus macOS `df` command where necessary | Capacity, available bytes, and mounted filesystem enumeration |
| Docker integration | Docker CLI through `subprocess.run` | Read-only Docker usage summary |
| Configuration/profiles | JSON using standard library `json` | Portable, validated, versioned profiles |
| Tests | `pytest` | Unit, CLI, and integration-style tests |
| Lint/format | Ruff | Consistent code quality |
| Packaging | `pyproject.toml` and setuptools | Editable development installation and installable CLI |

### 4.1 Dependency rules

- Keep runtime dependencies limited to Typer, Rich, Textual, and platformdirs. Do not add a dependency unless it materially reduces complexity or improves correctness.
- Use standard-library functionality before introducing another package.
- Do not use `psutil` for v1.0; the core product is disk analysis and can use the standard library and native macOS utilities.
- Import Textual lazily so ordinary CLI commands do not initialize the TUI.
- Avoid pinning every transitive dependency. Define sensible supported version ranges in `pyproject.toml`, and test the selected dependency set.
- Development dependencies should be optional and include pytest, pytest-cov, and Ruff.
- Do not require Homebrew for the application to run. Homebrew may be used by the developer to install Python or optional Docker tooling.

## 5. Supported Platform and Runtime Behavior

- Primary target: supported modern macOS releases on Apple Silicon and Intel Macs.
- Python runtime: Python 3.12+.
- Default shell on macOS: zsh.
- Support interactive zsh shell integration in v1.0. Implement bash integration as well if reliable; unsupported shells must receive a clear message and a documented fallback.
- Docker support is optional. All non-Docker features must work when Docker is not installed or is stopped.
- Do not require administrator privileges for ordinary inspection. If macOS permissions prevent reading an item, mark it as inaccessible and continue.
- Never run commands using `shell=True`. Pass argument arrays to subprocess calls, set timeouts, and check return codes.
- Use `LC_ALL=C` for parsing native command output when appropriate. Do not assume usernames, home paths, volume names, or locale-specific output are constant.

## 6. Product Identity and Terminal Theme

### 6.1 Color palette

Use the same palette in Rich output and the Textual TUI.

| Token | Hex | Usage |
|---|---|---|
| Primary mint | `#03FDC7` | Main accent, selected row, progress, key values, positive status |
| Primary text | `#FFFFFF` | Headings and primary content |
| Purple | `#A78BFA` | Metadata, paths, secondary labels, supporting details |
| Background | `#17151F` | TUI background only; do not force the user's terminal emulator background |
| Panel | `#252136` | TUI panels and modal surfaces |
| Border | `#514965` | Dividers and outlines |
| Warning | `#FBBF24` | Incomplete scans, permission limitations, warnings |
| Error | `#FF6B6B` | Errors and serious failures |
| Muted text | `#B9B4C9` | Hints and secondary descriptions |

Mint, white, and purple are the main brand colors. Warning and error colors are reserved for semantic states. Never communicate success, warning, or failure by color alone; also show a label or icon/text.

### 6.2 Terminal behavior

- Rich output must automatically respect non-interactive output and `NO_COLOR`.
- Do not emit ANSI color codes when output is piped, redirected, or `TERM=dumb` unless the user explicitly forces color.
- TUI uses the palette but must remain legible in supported terminal sizes and must not assume terminal truecolor support.
- Terminal resizing must not crash the application. At small sizes, hide low-priority columns and retain the main action/status.
- Use normal terminal conventions: Ctrl+C cancels an active scan or exits safely; `q` quits the TUI; Enter opens the selected detail.

## 7. Command-Line Interface Contract

The installed executable name is **`diskhawk`**. Command names and options below are the stable v1.0 interface.

### 7.1 Required commands

| Command | Behavior |
|---|---|
| `diskhawk` | Show a concise overview/help and example commands; do not launch an unexpected long scan |
| `diskhawk info` | Show the relevant disk summary |
| `diskhawk info --all` | Show all supported local mounted filesystems, filtering pseudo-filesystems by default |
| `diskhawk info --include-network` | Include network mounts in addition to the normal filesystem list |
| `diskhawk scan [PATH]` | Analyze a path; default path is the current working directory |
| `diskhawk scan [PATH] --top 20` | Show the top 20 largest files/directories; reject non-positive counts |
| `diskhawk scan [PATH] --min-size 100MB` | Filter displayed individual files/directories by minimum size |
| `diskhawk scan [PATH] --max-depth 4` | Limit report depth; document that a depth limit can make directory totals incomplete if traversal is also limited |
| `diskhawk scan [PATH] --json` | Emit a machine-readable scan result to stdout without decorative text |
| `diskhawk docker` | Show Docker disk usage if Docker is available |
| `diskhawk report` | Generate a sanitized disk diagnostic report and print/save its location |
| `diskhawk report --output PATH` | Save report to an explicit output path |
| `diskhawk report --format json` | Save a structured JSON report; human-readable text is also supported |
| `diskhawk report --include-details` | Include relative top-file/folder names after an explicit privacy confirmation in interactive mode; require a clear opt-in for non-interactive mode |
| `diskhawk profile export [PATH]` | Export the active portable configuration profile as JSON |
| `diskhawk profile import PATH` | Validate and import a profile; show a preview and ask for confirmation before changing the current profile |
| `diskhawk profile show` | Show active, non-secret settings |
| `diskhawk ui` | Launch the interactive TUI |
| `diskhawk ask TEXT...` | Parse supported natural-language disk phrases locally and route to the appropriate command |
| `diskhawk shell install zsh` | Safely install the zsh integration for the exact `give me disk info` phrase |
| `diskhawk shell uninstall zsh` | Remove only the DiskHawk-managed shell integration block |
| `diskhawk version` | Print the application version |
| `diskhawk --help` / `diskhawk COMMAND --help` | Show complete help for the CLI or command |

Implement `--help` and validation through Typer. Use consistent, actionable error messages and meaningful exit codes.

### 7.2 Natural-language phrases

Do not use an LLM or fuzzy, unpredictable interpretation. Normalize supported phrases by trimming whitespace, lowercasing, and collapsing repeated spaces. Support at minimum:

| Phrase passed to `diskhawk ask` | Action |
|---|---|
| `give me disk info` | Same summary as `diskhawk info` |
| `show disk info` | Same summary as `diskhawk info` |
| `disk info` | Same summary as `diskhawk info` |
| `check disk space` | Same summary as `diskhawk info` |
| `how much disk space is left` | Same summary as `diskhawk info` |
| `scan current folder` | Scan the current working directory |
| `find large files` | Scan the current working directory and show largest items |
| `docker disk usage` | Same result as `diskhawk docker` |

For unknown phrases, do not execute them as shell commands. Return a concise “I don't recognize that request” message plus the supported phrases and an example. Keep the phrase map in one isolated module with tests so it can be extended safely.

### 7.3 Exact shell phrase: `give me disk info`

The exact phrase must work only after the user explicitly installs shell integration. On macOS zsh:

1. User installs DiskHawk.
2. User runs `diskhawk shell install zsh`.
3. The installer explains which startup file it will update and creates a backup before modifying it.
4. The installer adds a clearly marked, idempotent managed block to `~/.zshrc`, unless a conflict is detected.
5. The managed function forwards the complete phrase to `diskhawk ask` without evaluating user text as code.
6. After the user opens a new terminal or reloads the shell configuration, typing `give me disk info` runs DiskHawk's disk summary.

Implementation behavior for the managed zsh function:

```zsh
give() {
  command diskhawk ask "give $*"
}
```

The agent must implement safe installation around this function; this code snippet alone is not the complete shell installer.

Safety requirements for shell integration:

- Never overwrite an existing `give` executable, alias, or function silently.
- Check PATH and relevant shell startup files for a likely naming conflict. If a conflict is detected or cannot be resolved safely, abort with instructions to use `diskhawk ask "give me disk info"` instead.
- Add a unique start/end marker. Repeated installs must not add duplicate blocks.
- Back up the existing startup file before editing it.
- Uninstall must remove only the exact DiskHawk-marked block and retain all unrelated content.
- Never use `eval` and never execute the phrase as arbitrary shell code.
- Document the phrase as an opt-in convenience, not a native shell command.

### 7.4 Exit codes

Use stable documented exit codes:

- `0`: successful command.
- `1`: unexpected internal or operational failure.
- `2`: invalid arguments or unsupported phrase.
- `3`: scan completed with partial results because of permission or transient filesystem errors.
- `4`: optional integration unavailable (for example Docker not installed or daemon unreachable), where the command cannot provide its requested result.

A command that returns partial results must clearly label them as partial. Avoid a traceback for expected user errors.

## 8. Disk Summary Requirements

### 8.1 Summary contents

`diskhawk info` and `give me disk info` must show:

- Host OS and architecture (for example macOS, arm64 or x86_64).
- Current disk summary for the filesystem containing `/` (startup/root), the user's home directory, and the current working directory, deduplicating entries that resolve to the same filesystem where possible.
- For each displayed filesystem: mount point, total capacity, used bytes, available bytes to the current user/system API, and usage percentage.
- A clear meter/bar in interactive output, plus numeric values so bars are not the only representation.
- A brief interpretation such as “X available of Y total” and a warning when usage exceeds a configurable threshold (default 90%).
- Whether optional Docker usage is available, but do not run Docker inspection implicitly if it would create a confusing delay. The user can run `diskhawk docker` explicitly.

Use `shutil.disk_usage()` and/or `os.statvfs()` for capacity values. When enumerating mounts on macOS, use a robust native approach (for example `df -Pk`) and parse paths containing spaces correctly. Handle multiple APFS mount points and firmlinks without claiming that each path is an independent physical disk. Do not double-add capacity across multiple mounts to invent a single “physical total.”

### 8.2 All-mounts view

`diskhawk info --all` lists supported mounted filesystems with capacity, used, available, usage percentage, and mount point. Exclude pseudo-filesystems/devices that are not useful disk volumes by default. Expose network mounts only when requested using `--include-network`. Avoid hiding ordinary external volumes. Add a short note about filtered mounts so the user understands that the view is curated.

### 8.3 Units and rounding

- Display human-readable binary units consistently: KiB, MiB, GiB, TiB, with one decimal place where useful.
- Use raw integer bytes in JSON output.
- Use the same base for all usage bars and percentages.
- Do not present rounded amounts as exact underlying values.

## 9. Recursive Directory Analysis

### 9.1 `diskhawk scan [PATH]`

- Default path: current working directory.
- Resolve and validate the path before traversal. If missing or not a directory, return a clear error (a file path may be accepted as a one-file inspection only if implemented consistently and documented).
- Display progress for interactive terminals. For non-interactive output, avoid animations and keep output deterministic.
- Identify the largest directories and files within the target tree, sorted by size descending by default.
- Show item type, relative path, logical size, allocated size when available, and scan status where appropriate.
- Provide total files/directories visited, inaccessible/error count, duration, and whether the result is complete.
- Use safe cancellation. Ctrl+C stops traversal cleanly, emits a summary stating that results are partial, and exits without corrupting output.

### 9.2 Size semantics

Directory sizes can be ambiguous on modern APFS filesystems. Implement and document these rules:

- **Logical size:** sum of file `st_size` values. This is the primary consistently available metric.
- **Allocated-size estimate:** where the platform exposes `st_blocks`, estimate allocated bytes as `st_blocks * 512`. If unavailable, show `N/A` rather than guessing.
- Do not label either value as guaranteed reclaimable space. APFS clones, compression, snapshots, hard links, open files, and filesystem metadata mean simple directory totals may differ from space reclaimed by deletion.
- Deduplicate hard-linked inodes within one scan when calculating the allocated-size estimate if practical; explain any limitations. Do not follow symlinks by default. Never traverse outside the chosen root through symlink targets.
- Never modify scanned files.

### 9.3 Exclusions and traversal safety

- Do not exclude `node_modules`, `.git`, `.venv`, build directories, or hidden folders by default: developers often need to find large development folders. They may be displayed with configurable ignore patterns.
- Do not follow symbolic links by default.
- Skip sockets, device files, and other non-regular file types from size totals unless separately labeled.
- Catch and count `PermissionError`, `FileNotFoundError`, and relevant `OSError` conditions. Continue scanning unaffected entries.
- Guard against symlink loops and transient directory changes.
- By default, do not recursively scan the filesystem root `/`. If the user explicitly requests `/`, require an additional explicit option such as `--allow-root`, show a warning, and allow cancellation before traversal.
- Expose `--exclude PATTERN` as a repeatable option and document whether the patterns match basenames or relative paths. Use a predictable, tested matching rule; do not interpret patterns as shell commands or regular expressions unless explicitly documented.
- Support `--max-depth` and `--top`. If a user elects to limit traversal depth, label the result as depth-limited and avoid presenting incomplete directory totals as full totals.
- Never promise exact scan completion time. Provide a progress indicator and a way to cancel.

### 9.4 Scan output example

The exact layout can be improved during implementation, but it must expose the following information in a clear table:

```text
DiskHawk / Directory Scan
Path: .
Status: COMPLETE

Largest items
TYPE   LOGICAL SIZE   ALLOCATED EST.   PATH
DIR    2.4 GiB        2.1 GiB          node_modules/
DIR    820 MiB        790 MiB          .git/
FILE   610 MiB        610 MiB          assets/archive.zip

Visited: 42,108 files · 4,203 directories · 3 inaccessible · 8.4 s
Note: directory sizes are estimates and may not equal reclaimable disk space.
```

Numbers above are illustrative only. Never hardcode example data into application output.

## 10. Docker Integration

### 10.1 Behavior

`diskhawk docker` is strictly read-only and must:

- Detect whether the `docker` executable exists.
- Run a bounded, non-interactive Docker disk-usage command using `subprocess.run` with an argument list and timeout.
- Report the active Docker context if available, and clearly indicate that usage may refer to a remote context rather than local Mac storage.
- Show available summary categories where supplied by Docker, including images, containers, local volumes, and build cache, with total size and reclaimable estimate when Docker provides it.
- Report “Docker is not installed,” “Docker daemon is unavailable,” “Docker command timed out,” or parsing limitations clearly, without crashing the rest of DiskHawk.
- Provide a concise remedy, such as checking that Docker Desktop is running, only when applicable.

### 10.2 Safety

- Do not run `docker system prune`, `docker volume prune`, `docker image prune`, `docker rm`, `docker stop`, or any destructive Docker command.
- Do not start Docker Desktop automatically.
- Do not inspect container environment variables, secrets, mounted file contents, or logs.
- Run only the documented read-only usage/context commands required for the summary.
- Handle Docker CLI versions with different output formats. Prefer structured formatting if the installed CLI supports it; otherwise use a small, isolated parser with tests and show a graceful “details unavailable” result if parsing fails.
- Never block indefinitely waiting for a daemon. Use a configurable sensible timeout (default 5 seconds for quick status, up to 15 seconds for detailed usage) and make timeout behavior visible.

## 11. Interactive TUI Specification

Launch with `diskhawk ui`. TUI is built with Textual and shares the same service layer as CLI commands. Do not duplicate disk-analysis logic inside UI widgets.

### 11.1 Main screen

The main screen contains:

1. Header: DiskHawk name, version, platform, and current view.
2. Summary panels: key capacity/available values and a usage meter.
3. A table/list of relevant filesystems or scan results, depending on the view.
4. Status/footer: progress, warnings, scan completion/errors, and key bindings.
5. Actions: refresh/rescan, search/filter, sort, inspect details, export report, help, and quit.

The TUI must have clear empty, loading, success, partial-result, unavailable, and failure states. It must never freeze the whole UI during recursive scans; run long scans in a Textual worker/background task and safely update the view from the supported UI mechanism.

### 11.2 Keyboard requirements

Implement and document these key bindings. Bindings must work when the main table/view has focus; text entry controls may keep normal text-editing behavior.

| Key | Action |
|---|---|
| `q` | Quit the TUI (if a scan is active, ask whether to cancel first or cancel safely) |
| `?` | Open help showing all supported bindings |
| `r` | Refresh disk information or rerun the current scan |
| `Enter` | Open details for the selected filesystem/file/folder |
| `Esc` | Close modal/dialog or clear the active search/filter when appropriate |
| `↑` / `↓` | Move selection |
| `j` / `k` | Move down/up when a text-entry widget does not have focus |
| `g` / `G` | Move to first/last table item |
| `/` | Focus search input |
| `s` | Cycle through documented sort options |
| `f` | Open filter controls |
| `e` | Export a sanitized report |
| `c` | Copy selected path where supported by the terminal/platform; otherwise show a clear unsupported message |
| `o` | Reveal selected path in Finder using macOS `open -R` for a valid local path; no shell interpolation |
| `Tab` / `Shift+Tab` | Move focus forward/backward through interactive controls |
| `Ctrl+C` | Cancel a running scan; if idle, exit cleanly |

Do not steal essential shortcuts from focused text inputs. Add automated tests for command/action mapping where feasible. If a key cannot be implemented robustly in Textual, provide an equivalent visible button and document the final binding accurately; do not document an unimplemented shortcut.

### 11.3 Mouse requirements

- Single-click a table row to select it.
- Double-click may open details if supported robustly by the selected Textual version; Enter must always open details.
- Mouse wheel/trackpad scrolling must move the table or main content.
- Buttons, tabs, filters, help, dialogs, and navigation controls must be clickable.
- Clicking a path row must not unexpectedly launch or modify a file. Opening Finder must require the explicit `o` action or a clearly labeled button.
- Keyboard-only operation must remain fully supported; no task may require a mouse.
- Keep focus visible and use the selected-row accent color plus a non-color indication.

### 11.4 Search and sorting

- Search/filter must operate on displayed paths and relevant names without rerunning the complete disk scan unless explicitly requested.
- Sort options must include size descending/ascending and name ascending/descending. Display the current sort direction.
- Clearing search restores the current result set.
- Refreshing while a scan is running must not launch duplicate scans. Either disable refresh while active or safely cancel/replace the prior task.

### 11.5 Small terminal and accessibility

- Target minimum usable size: 80 columns by 24 rows. Smaller terminals must show a concise resize hint and avoid layout crashes.
- Use high-contrast text and visible focus outlines.
- Provide labels in addition to icons/colors.
- Respect terminal resize events.
- No audio, blinking text, or excessive animations.

## 12. Reports and Environment/Profile Sharing

### 12.1 Sanitized report

`diskhawk report` produces a portable report locally. Default report must not include:

- Environment variable values or `.env` content.
- API keys, passwords, tokens, credentials, or keychain information.
- File contents.
- The user's full home-directory path or OS account name.
- A recursive inventory of individual filenames by default.
- Docker container environment variables, logs, or mount contents.

Default report content:

- Report schema version and DiskHawk version.
- UTC creation timestamp.
- OS family/version when available, architecture, and Python version.
- Disk capacity/used/available values and usage percentages for relevant filesystems.
- Whether Docker is available, and Docker disk usage summary only if the user explicitly requests Docker details or chooses the Docker report option.
- Scan statistics and aggregate sizes when available, without private paths or full filename listings.
- Warning/error counters and whether the result is partial.
- Active non-secret DiskHawk options that are safe to share.

Replace home-directory prefixes with `~` wherever a path is included. For report privacy, default to aggregate information only. `--include-details` is an explicit opt-in to include relative filenames and folder names; before writing details in an interactive terminal, display the data categories and ask for confirmation. For non-interactive output, require an explicit `--yes-include-details` or equivalent named flag; never silently include details.

JSON must have a documented, versioned schema with stable field names. Avoid embedding the full raw terminal output in JSON. Validate JSON by parsing it in tests. Text output must be readable without color and include a privacy note.

### 12.2 Configuration profile

Store app configuration using platformdirs in the user's per-user configuration directory. Do not require root. Use JSON with a schema version so no extra TOML-writing dependency is needed.

Permitted settings include:

- `warning_threshold_percent` (default 90; allowed range 1–100).
- Default `top` result count (default 20; bounded to a reasonable range such as 1–500).
- Default ignore patterns, if any.
- Color preference (`auto`, `always`, `never`).
- Whether Docker integration is enabled for explicit Docker commands/reports.
- Default report format and report directory preference.
- Optional display preferences such as compact table mode.

Do not store credentials, `.env` values, private keys, or environment-variable contents.

### 12.3 Profile import/export safety

- Export only documented configuration keys, with `schema_version` and app name.
- Import must parse JSON, validate schema and types, reject unsupported future schema versions, reject unknown keys or explicitly warn and ignore them according to one documented policy, and reject invalid values.
- Show a diff/preview of settings changes and require confirmation before applying an imported profile.
- Imported data is configuration data only; never execute code or shell commands from it.
- Exported profiles must not include absolute user paths by default. Use portable relative values where a path setting is necessary.
- Write configuration atomically via a temporary file followed by replace. Preserve a backup of the previous config before changing it.
- If the profile is invalid, do not partially update the current configuration.

## 13. Configuration, Files, and Project Structure

Use the following structure or a cleaner structure with the same separation of concerns. Do not collapse all logic into one large file.

```text
diskhawk/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── src/
│   └── diskhawk/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── commands/
│       │   ├── __init__.py
│       │   ├── info.py
│       │   ├── scan.py
│       │   ├── docker.py
│       │   ├── report.py
│       │   ├── profile.py
│       │   ├── ask.py
│       │   └── shell.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── disk_info.py
│       │   ├── scanner.py
│       │   ├── size_format.py
│       │   ├── docker_info.py
│       │   ├── phrase_router.py
│       │   ├── reports.py
│       │   └── models.py
│       ├── config/
│       │   ├── __init__.py
│       │   ├── manager.py
│       │   ├── schema.py
│       │   └── profiles.py
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── screens.py
│       │   ├── widgets.py
│       │   └── theme.tcss
│       ├── shell_integration/
│       │   ├── zsh.zsh
│       │   └── bash.bash
│       └── utils/
│           ├── __init__.py
│           ├── subprocesses.py
│           └── privacy.py
├── tests/
│   ├── unit/
│   ├── cli/
│   ├── integration/
│   └── fixtures/
└── docs/
    ├── commands.md
    ├── privacy.md
    ├── docker.md
    └── troubleshooting.md
```

### 13.1 Separation of concerns

- `cli.py` builds the Typer app and registers command modules.
- `core/` contains reusable business logic that can be tested without rendering a terminal UI.
- `commands/` adapts core results to CLI input/output and exit codes.
- `tui/` presents the same core services through Textual. UI widgets must not implement their own disk traversal.
- `config/` owns the schema, defaults, loading, validation, import/export, backups, and atomic writes.
- `utils/subprocesses.py` centralizes safe subprocess invocation, timeouts, return-code handling, and output limits.
- `utils/privacy.py` owns path sanitization and report redaction. Do not duplicate redaction logic across commands.

### 13.2 Data models

Use typed dataclasses or similarly lightweight typed structures for at least:

- `FilesystemInfo`: source/device (internal only where useful), mount point, total bytes, used bytes, available bytes, usage percentage, filesystem type if known, and any warning/metadata.
- `ScanEntry`: relative path, entry type, logical bytes, allocated bytes or `None`, depth, and optional errors/status.
- `ScanSummary`: root, start/end/duration, files/directories visited, inaccessible/error counts, completion state, top entries, and whether depth/entry limits applied.
- `DockerUsage`: availability state, context (if safely obtained), category totals, reclaimable estimate when available, and warnings.
- `DiskHawkReport`: schema version, app/platform metadata, filesystem summaries, aggregate scan stats, optional Docker summary, warnings, and sanitized settings.
- `DiskHawkConfig`: validated non-secret configuration settings and schema version.

Store raw absolute paths only in local in-memory scan results as required. Sanitize them at report/export boundaries. Do not store scan history persistently in v1.0.

## 14. Error Handling and Security

- Expected operational errors must be shown as concise user-facing messages, not stack traces. Full debug details may be shown only with an explicit `--debug` flag; do not include secret values in debug output.
- Use subprocess argument lists and timeouts; never `shell=True`, `eval`, or command-string concatenation.
- Limit external command output size when feasible and handle malformed output safely.
- Validate all paths and option values. Normalize paths carefully; do not follow symlinks outside scan root.
- Never silently elevate privileges or request administrator passwords.
- Never modify disk files, permissions, Docker resources, shell configuration, or user config except in explicit commands designed for that purpose.
- Shell integration install/uninstall must state the target file, back up before edits, use managed markers, and preserve unrelated content.
- Profile import must not execute imported content.
- Report output must default to a safe local path and never overwrite an existing report without confirmation. In non-interactive mode, require an explicit overwrite option when the target exists.
- Avoid logging private absolute paths unless necessary for an explicit local diagnostic; sanitize report output by default.
- If a scan is partial, retain valid results and make incompleteness obvious.

## 15. Performance and Reliability Targets

These are design targets to validate on a normal developer Mac, not guarantees for every filesystem:

- `diskhawk --help`, `diskhawk version`, and `diskhawk info` should return quickly and must not recursively walk directories.
- `diskhawk info` should not initialize Textual or query Docker unless requested.
- TUI should stay responsive while scanning; scan work runs in a worker and progress updates are throttled to avoid excessive UI updates.
- Avoid keeping a full record for every file if doing so creates excessive memory use. Maintain bounded top-N results with a heap where practical, plus aggregate counters.
- Avoid repeatedly statting the same file or running multiple `df` processes per row. Batch native calls where possible.
- All subprocess calls have timeouts and controlled output handling.
- Large directory scans can be cancelled without a crash; already collected results can be summarized as partial.
- No persistent background process remains after a CLI command exits.

## 16. Testing Requirements

Implement tests alongside the product, not after all code is written. Tests must not depend on the developer's personal disk contents or require Docker to be installed.

### 16.1 Unit tests

Cover at least:

- Human-readable size formatting and byte/percentage calculations, including zero/unknown capacity.
- Disk output parsing with normal output, paths containing spaces, missing columns, malformed output, and non-zero native command exit.
- Deduplication of duplicate mounts where applicable.
- Scanner behavior for nested files/folders, hidden files, symlinks, hard links, unreadable items, files removed during scanning, empty directories, permission errors, exclusions, max depth, and cancellation.
- Correct distinction between logical and allocated-size estimates.
- Stable sorting and top-N selection.
- Natural-language normalization, every supported phrase, repeated spaces, case differences, and unsupported phrases.
- Configuration defaults, invalid values, unknown keys, schema mismatch, atomic writes, import rollback, and export validation.
- Path sanitization (home path replacement and no raw environment values).
- Docker parsing, timeout, missing CLI, daemon-unavailable status, and malformed output using mocks.
- Shell integration conflict detection, idempotent install, backup behavior, and removal of only the marked block.

### 16.2 CLI tests

Use Typer's test runner or an equivalent CLI harness to verify:

- Every required command exists and has working help.
- `diskhawk info` produces useful, parseable output using mocked disk data.
- `diskhawk scan` handles paths and invalid options.
- `diskhawk ask "give me disk info"` routes to the disk summary.
- `diskhawk docker` degrades gracefully when Docker is missing.
- `diskhawk report` writes valid sanitized output.
- Profile export/import workflows and confirmation behavior.
- Exit codes match the contract.
- Non-TTY output contains no forced ANSI escapes unless explicitly requested.

### 16.3 TUI tests

Use Textual's supported testing tools to check:

- TUI launches and displays disk summary.
- Keyboard navigation, help, search, sorting, escape, refresh, report export, and quit behavior.
- Mouse row selection and clickable controls where supported by the Textual test API.
- Scan work does not block the UI thread.
- Errors and empty states render without crashing.
- Small terminal layout remains usable.

### 16.4 Integration tests

- Run end-to-end scan against a temporary directory created by tests.
- Test shell-integration modifications in temporary startup-file fixtures; never modify the developer's actual shell files during automated tests.
- If Docker is present, optional integration tests may run read-only checks. Otherwise skip them with an explicit reason.
- Tests must not require `sudo`, network access, cloud credentials, or a live Docker daemon.

### 16.5 Quality gates

Before completion, run and fix failures from:

```bash
python -m pytest
ruff check .
ruff format --check .
```

Add coverage reporting and target at least 85% line coverage for core logic (`core/`, `config/`, and privacy utilities). Do not game coverage by testing only trivial lines. TUI visual layout can have a smaller coverage percentage if all important interaction paths are tested.

## 17. Installation and Developer Experience

### 17.1 Development setup

Document a clean macOS path:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest
```

The `pyproject.toml` must define the `diskhawk` console script entry point. The commands above must work from a fresh checkout.

### 17.2 User installation

Document installation with an isolated Python CLI installer such as `pipx`:

```bash
python3 -m pip install --user pipx
python3 -m pipx ensurepath
pipx install .
```

If pipx is not available or Python's environment differs, document a tested alternative. Do not tell users to use `sudo pip install`. The packaging must install `diskhawk` and all runtime dependencies without relying on the repository directory after installation.

### 17.3 Enable exact phrase

Document these opt-in commands after installation:

```bash
diskhawk shell install zsh
```

Then open a new terminal and type:

```text
give me disk info
```

Also document the fallback that does not need shell integration:

```bash
diskhawk ask "give me disk info"
```

Explain how to uninstall the integration:

```bash
diskhawk shell uninstall zsh
```

Test the real integration manually on a clean temporary zsh profile before marking it complete. Automated tests must use temporary files and must not alter a developer's actual `.zshrc`.

## 18. Documentation Deliverables

The repository must include:

- `README.md`: what DiskHawk does, feature overview, requirements, installation, quick start, command examples, theme preview, safety/privacy guarantees, limitations, and troubleshooting.
- `docs/commands.md`: each command, options, defaults, examples, output meanings, and exit codes.
- `docs/privacy.md`: exactly what reports include/exclude, path sanitization, and explicit detail opt-in.
- `docs/docker.md`: requirements, Docker context caveat, read-only behavior, timeout behavior, common errors.
- `docs/troubleshooting.md`: command not found, PATH issues, shell integration conflict, unsupported shell, permission errors, Docker unavailable, and scan partial results.
- `CHANGELOG.md`: v1.0.0 changes.
- `CONTRIBUTING.md`: setup, tests, lint, formatting, and contribution expectations.
- `LICENSE`: include a standard open-source license only if the project owner has chosen one; otherwise add a clear decision note to the completion summary rather than inventing ownership or licensing terms. Do not block technical implementation on a license choice.

Documentation must match actual implemented behavior. Do not claim a shortcut, command, shell, Docker output, privacy guarantee, or option is supported unless tests or implementation confirm it.

## 19. Acceptance Criteria — Definition of Done

The v1.0 build is complete only when all applicable requirements below pass:

### Core behavior
- [ ] `diskhawk info` displays accurate current filesystem capacity, used, available, and percentage values without scanning directories.
- [ ] The output identifies relevant startup/home/current-working-directory filesystems and avoids double-counting duplicate mounts.
- [ ] `diskhawk info --all` and `--include-network` work as documented.
- [ ] `diskhawk scan .` detects large files/directories and reports logical size plus allocated-size estimate when available.
- [ ] Scanner does not follow symlinks, does not modify files, and keeps working when individual items are inaccessible or disappear.
- [ ] Partial scans and depth limits are clearly labeled.
- [ ] `diskhawk docker` is read-only, bounded by a timeout, and works gracefully when Docker is missing or stopped.
- [ ] `diskhawk ask "give me disk info"` produces the same essential result as `diskhawk info`.
- [ ] After safe shell integration installation and opening a new shell, `give me disk info` works exactly as requested, unless a naming conflict is detected; conflict behavior is documented and safe.

### TUI and theme
- [ ] TUI uses mint `#03FDC7`, white `#FFFFFF`, purple `#A78BFA`, charcoal/panel tones, and semantic warning/error colors consistently.
- [ ] Keyboard controls, mouse selection, scrolling, search, sorting, details, refresh, export, help, and quitting work.
- [ ] Long scans run without blocking the TUI; cancellation is safe.
- [ ] Color is disabled/adapted correctly for `NO_COLOR`, non-TTY output, and `TERM=dumb`.

### Sharing and safety
- [ ] Default reports are sanitized, valid, versioned JSON or readable text, with no environment variable values or secret content.
- [ ] Detailed filename sharing requires explicit user opt-in.
- [ ] Profile import is schema-validated, previewed, confirmed, and atomic; invalid profiles do not partially apply.
- [ ] Shell integration is opt-in, conflict-aware, backed up, idempotent, and cleanly uninstallable.
- [ ] No destructive file or Docker operation exists in v1.0.
- [ ] No network, AI API, telemetry, or background daemon is required.

### Engineering quality
- [ ] Application is packaged and installs the `diskhawk` command from a clean checkout.
- [ ] All required commands have help text and predictable exit codes.
- [ ] Unit/CLI/TUI/integration tests described in Section 16 are implemented to a reasonable level and pass.
- [ ] Ruff lint and format checks pass.
- [ ] Core-logic test coverage is at least 85%, with any shortfall justified in the final summary.
- [ ] README and supporting docs match the implemented features.
- [ ] No TODO placeholders, fake sample values in live output, unimplemented menu actions, dead buttons, or known failing tests remain.

## 20. Implementation Order for the Coding Agent

Complete the project in these stages, keeping the repository runnable after each stage. Do not stop at an intermediate stage.

1. **Inspect the workspace.** Check existing files and preserve unrelated user work. If an existing project already exists, integrate the design cleanly rather than overwriting files blindly.
2. **Create packaging and models.** Set up `pyproject.toml`, CLI entry point, typed models, defaults, and theme constants.
3. **Implement filesystem summary.** Build and test mount enumeration, byte math, formatting, filtering, and error behavior.
4. **Implement scanner.** Add traversal safety, sizing semantics, top-N selection, limits, progress callbacks, cancellation, and tests.
5. **Implement Docker adapter.** Add safe subprocess wrapper, timeouts, parsing, context caveat, and mocked tests.
6. **Implement config/privacy/reports.** Add validated config, atomic updates, portable profiles, sanitization, versioned JSON, text report, and tests.
7. **Implement CLI commands and phrase parser.** Register every required command, output format, exit code, help text, and phrase test.
8. **Implement shell integration.** Add opt-in installation/uninstallation, markers, conflict detection, backups, and isolated tests.
9. **Implement TUI.** Use existing core services. Add screens, theme, keyboard/mouse controls, background scanning, progress, cancellation, help, and UI tests.
10. **Package and document.** Ensure a clean install works and finish README, reference docs, changelog, troubleshooting, and developer instructions.
11. **Run quality gates.** Run all tests, lint, format checks, coverage, and packaging/install smoke tests; fix all implementation failures instead of leaving notes for later.
12. **Perform end-to-end verification.** Verify `diskhawk info`, scan of a temporary fixture, phrase routing, report export/import, TUI startup/basic bindings, Docker-unavailable behavior, and shell integration against temporary shell config files. Manually verify the exact phrase in a clean zsh session where feasible.

## 21. Final Instructions to the Coding Agent

Treat this document as the implementation source of truth. Use reasonable engineering judgment for minor choices, but do not omit requirements or stop to ask for approval on details already specified here. Do not replace the product with a simpler demo or only generate an architecture document.

At completion, provide a concise implementation report containing:

1. Main features implemented.
2. Project tree and important files.
3. Exact installation and run commands.
4. How to enable and remove `give me disk info` shell integration.
5. Tests, lint, formatting, coverage, and packaging checks actually run, including their real results.
6. Any limitations that remain, with no claims that untested features work.

**Do not declare completion until the Definition of Done in Section 19 has been checked against the actual code and test results.**
