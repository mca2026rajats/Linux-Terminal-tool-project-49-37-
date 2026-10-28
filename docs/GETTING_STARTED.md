# DiskHawk: step-by-step run guide

This guide walks through setting up DiskHawk on macOS, checking that it works,
and using its CLI, TUI, reports, profiles, and optional shell phrase.

## 1. Open the project folder

Open Terminal and change to the directory containing `pyproject.toml`:

```bash
cd "/Users/rajatsonar/LINUX Project 2"
```

If you put the project somewhere else, replace that path with your checkout's
location.

## 2. Check Python

DiskHawk requires Python 3.12 or newer:

```bash
python3 --version
```

If the reported version is below 3.12 or Python is not found, install a newer
Python using a method you trust, then open a fresh terminal. Do not use
`sudo pip install`.

## 3. Create and activate a virtual environment

Run these commands from the project directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt may now show `(.venv)`. The environment keeps DiskHawk's packages
separate from the rest of your machine. Any time you open a new terminal to
work on the project, repeat the `cd` and `source .venv/bin/activate` commands.

## 4. Install DiskHawk and development tools

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

The editable install makes the `diskhawk` command available in the active
virtual environment and uses the source files in this checkout.

## 5. Confirm the installation

```bash
diskhawk --help
diskhawk version
```

You should see the command list and `DiskHawk 1.0.0`. If the shell says
`diskhawk: command not found`, first check that `.venv` is active. You can also
run it directly as `./.venv/bin/diskhawk`.

## 6. Check your disk summary

```bash
diskhawk info
```

This displays the pixel-art capacity dashboard with filesystem volume/mount,
used and available space, total capacity, percentages, and a segmented usage
bar. It also samples separate physical disk read/write counters over about one
second on macOS and shows the measured average throughput. This is not a
benchmark; virtual or disk-image volumes and systems without accessible IOKit
counters show `N/A` instead. These are physical-device totals, so activity from
other volumes sharing the same device is included and is not attributed to an
individual APFS mount. `diskhawk info` does not recursively scan folders or
query Docker. The footer confirms the operation is read-only and that hardware
health is not assessed.

To emit JSON byte counts for another program:

```bash
diskhawk info --json
```

The JSON mode remains immediate and does not wait for a live activity sample.

To view the curated mounted filesystem list:

```bash
diskhawk info --all
```

Add `--include-network` if you also want network mounts. Filesystem capacities
for multiple APFS mounts are not added together as though they were separate
physical disks.

## 7. Find large files and directories

Scan the current project directory:

```bash
diskhawk scan .
```

Scan another directory:

```bash
diskhawk scan ~/Downloads
```

Useful options:

```bash
diskhawk scan . --top 10
diskhawk scan . --min-size 100MB
diskhawk scan . --max-depth 3 //Fix
diskhawk scan . --exclude '*.cache' //fix
diskhawk scan . --json
```

In an interactive terminal, `diskhawk scan` shows a live pixel-art scan panel
with actual file/directory counts, elapsed time, inaccessible paths, and current
path. It does not estimate a completion percentage. Afterward, the results
dashboard lists the largest items by logical size. Redirected and JSON output
remain static; JSON output keeps its existing structure. Scanning `/` or a
mounted filesystem root is labeled separately from an ordinary directory scan.

The scan is read-only and does not follow symbolic links. Hidden files and
directories such as `.git` are included unless excluded. Logical sizes and
allocated-size estimates are useful for diagnosis but are not guarantees of
reclaimable space. Incomplete scans report partial results and return exit code
3. DiskHawk refuses to scan `/` without `--allow-root`; in a terminal it also
asks you to confirm.

## 8. Launch the interactive terminal UI

```bash
diskhawk ui
```

Use the arrow keys or `j`/`k` to move. Press Enter for details, `/` to search,
`s` to change sorting, `r` to refresh, `e` to export a sanitized report, `?`
for help, and `q` to quit. Select **Scan current folder** to run a background
scan. Ctrl+C cancels the active scan; a cancellation returns partial results.

The TUI is intended for terminals at least 80 columns wide and 24 rows tall.
For key bindings, see the help screen and
[command reference](./commands.md).

## 9. Use the exact phrase without shell changes

Phrase matching works directly through DiskHawk and needs no shell integration:

```bash
diskhawk ask "give me disk info"
diskhawk ask "find large files"
diskhawk ask "docker disk usage"
```

DiskHawk recognizes only its documented phrases. It does not send text to an AI
or execute unknown text as a command.

## 10. Optionally enable `give me disk info` in your shell

For zsh, the default macOS shell:

```bash
diskhawk shell install zsh
```

The installer prints the startup-file path, checks for conflicts, backs up the
file, then adds a marked DiskHawk block. It does not overwrite an existing
`give` command, alias, or function. Open a new terminal (or load the startup
file) and type:

```text
give me disk info
```

To remove the integration later:

```bash
diskhawk shell uninstall zsh
```

On macOS, bash integration uses `~/.bash_profile`:

```bash
diskhawk shell install bash
diskhawk shell uninstall bash
```

If there is a naming conflict, use the direct `diskhawk ask "give me disk info"`
form instead. Shell integration is optional.

## 11. Optional Docker disk usage

If Docker CLI is installed and its configured daemon is reachable:

```bash
diskhawk docker
```

DiskHawk runs read-only usage/context commands with a timeout. It does not start
Docker, prune data, stop containers, or change Docker settings. The selected
Docker context may be remote; its reported usage may not belong to this Mac.
All other DiskHawk features work without Docker.

## 12. Create a diagnostic report

Write a local text report:

```bash
diskhawk report --output ./diskhawk-report.txt
```

Write versioned JSON:

```bash
diskhawk report --format json --output ./diskhawk-report.json
```
 
Add aggregate information from an explicitly chosen folder:

```bash
diskhawk report --format json --scan-path ~/Downloads --output ./diskhawk-report.json
```

Docker information is opt-in:

```bash
diskhawk report --docker --format json --output ./diskhawk-report.json
```

By default, reports exclude filenames and shorten home paths. Existing output
files are not silently replaced; use `--force` when you intentionally want to
overwrite one.

To include relative names from the top scan entries, explicitly request both
the scan and detailed data:

```bash
diskhawk report \
  --scan-path ~/Downloads \
  --include-details \
  --yes-include-details \
  --format json \
  --output ./diskhawk-report-details.json
```

`--yes-include-details` is required for non-interactive use. Treat detailed
reports as potentially identifying and review them before sharing. See the
[privacy guide](./privacy.md) for the exact report fields and exclusions.

## 13. View, export, or import settings profiles

Show the active non-secret settings:

```bash
diskhawk profile show
```

Export a portable profile:

```bash
diskhawk profile export ./diskhawk-profile.json
```

Validate, preview, and import a profile:

```bash
diskhawk profile import ./diskhawk-profile.json
```

The import command asks for confirmation before applying valid settings. For a
trusted profile in a non-interactive script, add `--yes`. Imports are data-only;
they are not run as code.

## 14. Run tests and quality checks

From the activated project environment:

```bash
python -m pytest
python -m pytest --cov
ruff check .
ruff format --check .
```

Tests use temporary files and mocks; they do not need a live Docker daemon,
network access, or administrator access.

## 15. Build an installable wheel (optional)

```bash
python -m pip wheel --no-deps --wheel-dir dist .
```

The wheel is written to `dist/`. To test the installed command in a clean
environment, use `pipx` if it is available:

```bash
pipx install .
diskhawk --help
```

The `pipx` command is optional and is separate from the project-local
`.venv` workflow.

## 16. Leave the project environment

When finished, deactivate the virtual environment:

```bash
deactivate
```

This only leaves the environment; it does not uninstall DiskHawk or delete any
project files.

For complete command options and exit codes, see [commands](./commands.md).
For common setup or permission issues, see [troubleshooting](./troubleshooting.md).
