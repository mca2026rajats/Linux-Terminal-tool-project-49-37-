# Docker integration

Docker is optional. `diskhawk docker` detects the CLI and requests a read-only
`docker system df` summary, with a bounded timeout. It reports categories and
reclaimable estimates only when the installed CLI provides parseable data.

The command also reads the active Docker context. A context can point to a
remote daemon, so its usage must not automatically be interpreted as usage on
the current Mac. DiskHawk does not start Docker Desktop, inspect container
environment variables, logs, or mounted contents, or run prune/stop/remove
commands.

`diskhawk info` does not query Docker. A report includes Docker data only when
`diskhawk report --docker` is explicitly requested.

Possible states include Docker CLI missing, daemon/context unavailable, timeout,
or details unavailable because output could not be parsed. Start Docker Desktop
or select the intended context yourself if appropriate, then retry. DiskHawk
does not change Docker configuration.
