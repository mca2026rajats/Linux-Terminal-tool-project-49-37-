# DiskHawk

DiskHawk is a local-first macOS terminal utility for understanding disk capacity,
finding large files and directories, and creating privacy-conscious diagnostics.
It provides a scriptable CLI and an interactive Textual TUI. It does not use AI,
network services, accounts, telemetry, or a background daemon.

## Requirements

- macOS on Apple Silicon or Intel
- Python 3.12 or newer
- Docker CLI only for the optional, read-only Docker usage command

DiskHawk uses Python, Typer, Rich, Textual, and platformdirs. Ordinary disk
summary and scan functions do not require Docker or administrator privileges.

## Install for development

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest
```

For an isolated user installation, install `pipx` with your preferred package
manager and run:

```bash
pipx install .
```

The package installs the `diskhawk` command and does not rely on the source
checkout after installation.

## Quick start

```bash
diskhawk info
diskhawk info --all
diskhawk scan .
diskhawk docker
diskhawk report --format json --output ./diskhawk-report.json
diskhawk profile show
diskhawk ui
```

Run `diskhawk --help` or `diskhawk COMMAND --help` for complete options.

## Interactive interface

Run `diskhawk ui`. Use arrow keys (or `j`/`k`) to navigate, Enter for details,
`/` or `f` to filter, `s` to change sort, `r` to refresh, `e` to export a
sanitized report, `?` for help, and `q` to quit. The mint accent is `#03FDC7`,
with white primary text and purple metadata on charcoal panels. Color is adapted
to the terminal.

The scan button analyzes the current directory in a background worker. Scans are
read-only and can be cancelled with Ctrl+C. Directory totals are logical-size
estimates and are not guarantees of reclaimable space.

## Local phrase routing

The deterministic phrase router supports a small documented phrase set. For
example:

```bash
diskhawk ask "give me disk info"
diskhawk ask "find large files"
diskhawk ask "docker disk usage"
```

It does not interpret arbitrary text as a command and does not use an AI
service.

To opt into the exact `give me disk info` shell phrase in zsh:

```bash
diskhawk shell install zsh
```

The installer checks for conflicts, backs up the startup file, and adds a
managed block. Open a new terminal, then type `give me disk info`. Remove it
later with:

```bash
diskhawk shell uninstall zsh
```

The same opt-in workflow is available for bash. See
[troubleshooting](./docs/troubleshooting.md) for conflicts and shell setup.

## Safety and privacy

- Disk and file inspection is read-only. DiskHawk never deletes files, prunes
  Docker resources, stops containers, or changes permissions.
- Directory scans do not follow symbolic links and continue after individual
  access errors. APFS clones, compression, snapshots, hard links, and metadata
  mean scan sizes may differ from reclaimable space.
- Docker inspection is explicit (`diskhawk docker` or `diskhawk report --docker`)
  and uses the configured Docker context, which may be remote.
- Reports omit filenames by default, shorten home paths, and never read
  environment values, `.env` files, secrets, file contents, logs, or container
  environment variables. Detailed names require explicit opt-in.
- Configuration profiles contain only validated DiskHawk preferences. Imported
  JSON is never executed.

See [privacy](./docs/privacy.md), [Docker behavior](./docs/docker.md), and
[commands](./docs/commands.md) for full details and limitations.

## Project resources

- [Step-by-step run guide](./docs/GETTING_STARTED.md)
- [Command reference](./docs/commands.md)
- [Privacy model](./docs/privacy.md)
- [Docker integration](./docs/docker.md)
- [Troubleshooting](./docs/troubleshooting.md)
- [Contributing](./CONTRIBUTING.md)

No license has been selected for this project; do not assume reuse or
redistribution permissions.
