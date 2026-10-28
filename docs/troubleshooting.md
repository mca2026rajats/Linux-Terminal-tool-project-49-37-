# Troubleshooting

## `diskhawk`: command not found

Confirm installation succeeded and the installer directory is on `PATH`. For
development, activate `.venv` or use `.venv/bin/diskhawk`. A `pipx` install
keeps the app isolated; run `pipx ensurepath` if its executable directory is
missing.

## Python/dependency installation

DiskHawk requires Python 3.12 or newer. Use an isolated virtual environment and
avoid `sudo pip install`. If a dependency does not yet support your Python
runtime, use a supported Python interpreter in a dedicated environment rather
than changing the system Python.

## Shell phrase not recognized

The phrase `give me disk info` is opt-in. Run `diskhawk shell install zsh` or
`diskhawk shell install bash`, then open a new shell or source the configured
startup file (`~/.zshrc` for zsh; `~/.bash_profile` for bash on macOS). The
installer also checks related shell startup files for conflicts. It will not overwrite a `give` executable, alias, or
function. In that case use:

```bash
diskhawk ask "give me disk info"
```

Uninstall with `diskhawk shell uninstall zsh` (or `bash`). Only the exact
DiskHawk-marked block is removed; a backup is created before modification.

## Permission errors or partial scans

macOS privacy controls can prevent reading some directories. DiskHawk does not
request administrator privileges; inaccessible or disappearing items are
counted and scanning continues. Partial results are labeled and return exit
code 3. Grant access only through macOS settings if you choose to do so.

## Docker unavailable

The CLI may be absent, the configured daemon may be stopped/unavailable, the
command may time out, or the active context may be remote. DiskHawk reports
these states and does not start Docker or change contexts. All non-Docker
features work without it.

## TUI layout

Use a terminal at least 80 columns by 24 rows. Resize smaller terminals when the
status line shows a resize hint. The TUI scan runs in a worker; Ctrl+C requests
safe cancellation.
