from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.live import Live

from diskhawk import __version__
from diskhawk.commands.shell import (
    ShellIntegrationError,
    install_shell_integration,
    startup_file,
    uninstall_shell_integration,
)
from diskhawk.config.manager import load_config, save_config
from diskhawk.config.profiles import export_profile, import_profile
from diskhawk.core.disk_activity import sample_disk_activity
from diskhawk.core.disk_info import (
    list_filesystems,
    platform_label,
    relevant_filesystems,
    supported_filesystems,
)
from diskhawk.core.docker_info import get_docker_usage
from diskhawk.core.models import DiskHawkConfig, ScanSummary
from diskhawk.core.phrase_router import Action, route_phrase, supported_phrases
from diskhawk.core.reports import build_report, render_json, render_text
from diskhawk.core.scanner import ProgressEventCallback, ScanProgress, scan_directory
from diskhawk.core.size_format import format_bytes, parse_size
from diskhawk.presentation.pixel_dashboard import dashboard_console, render_pixel_disk_info
from diskhawk.presentation.scan_dashboard import (
    LiveScanView,
    render_scan_failure,
    render_scan_results,
)
from diskhawk.theme import THEME

app = typer.Typer(
    name="diskhawk",
    help="Local-first disk diagnostics for macOS.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
profile_app = typer.Typer(help="Show and share portable DiskHawk settings.")
shell_app = typer.Typer(help="Install or remove opt-in shell phrase integration.")
app.add_typer(profile_app, name="profile")
app.add_typer(shell_app, name="shell")
console = Console(theme=THEME)


def _configure_console(color: str) -> None:
    global console
    console = Console(
        theme=THEME,
        force_terminal=color == "always",
        no_color=color == "never",
    )


def _config() -> DiskHawkConfig:
    try:
        config = load_config()
        _configure_console(config.color)
        return config
    except ValueError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.callback()
def main(
    ctx: typer.Context,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=lambda value: _version(value), is_eager=True),
    ] = None,
) -> None:
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


def _version(value: bool) -> bool:
    if value:
        typer.echo(f"DiskHawk {__version__}")
        raise typer.Exit()
    return value


@app.command()
def version() -> None:
    """Print the DiskHawk version."""
    typer.echo(f"DiskHawk {__version__}")


@app.command()
def info(
    all_filesystems: Annotated[
        bool, typer.Option("--all", help="List curated mounted filesystems.")
    ] = False,
    include_network: Annotated[
        bool, typer.Option("--include-network", help="Include network mounts.")
    ] = False,
    threshold: Annotated[int | None, typer.Option("--threshold", min=1, max=100)] = None,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit JSON without decorative output.")
    ] = False,
) -> None:
    """Show capacity for the startup, home, and current-working-directory filesystems."""
    config = _config()
    try:
        mounts = list_filesystems()
        rows = (
            supported_filesystems(mounts, include_network=include_network)
            if all_filesystems or include_network
            else relevant_filesystems(mounts)
        )
    except RuntimeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "platform": platform_label(),
                    "docker_cli_available": bool(shutil.which("docker")),
                    "filesystems": [
                        {
                            "mount_point": item.mount_point,
                            "total_bytes": item.total_bytes,
                            "used_bytes": item.used_bytes,
                            "available_bytes": item.available_bytes,
                            "usage_percent": round(item.usage_percent, 2),
                        }
                        for item in rows
                    ],
                },
                indent=2,
            )
        )
    else:
        dashboard = dashboard_console(file=sys.stdout, color=config.color)
        try:
            render_pixel_disk_info(
                rows,
                console=dashboard,
                warning_threshold_percent=threshold or config.warning_threshold_percent,
                activity=sample_disk_activity(rows),
                view_note=(
                    "MOUNT VIEW  Pseudo-filesystems are filtered; network mounts are shown only "
                    "when requested. Mounted volumes may share APFS capacity; "
                    "values are not additive."
                    if all_filesystems or include_network
                    else None
                ),
            )
        except ValueError as exc:
            typer.echo(f"Disk information unavailable: {exc}", err=True)
            raise typer.Exit(1) from exc


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Argument(help="Directory to inspect.", exists=True),
    ] = Path("."),
    top: Annotated[int | None, typer.Option("--top", min=1, max=500)] = None,
    min_size: Annotated[
        str, typer.Option("--min-size", help="Minimum displayed size, e.g. 100MB.")
    ] = "0B",
    max_depth: Annotated[int | None, typer.Option("--max-depth", min=0)] = None,
    exclude: Annotated[
        list[str] | None, typer.Option("--exclude", help="Exclude basename or relative-path glob.")
    ] = None,
    allow_root: Annotated[
        bool, typer.Option("--allow-root", help="Allow scanning / after explicit confirmation.")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON.")
    ] = False,
) -> None:
    """Find the largest files and directories without modifying them."""
    config = _config()
    if path.resolve(strict=False) == Path("/") and allow_root and sys.stdin.isatty():
        if not typer.confirm("Scanning / can take a long time. Continue?"):
            raise typer.Exit(2)
    scan_console = dashboard_console(file=sys.stdout, color=config.color)

    def run_scan(*, progress_event: ProgressEventCallback | None = None) -> ScanSummary:
        return scan_directory(
            path,
            top=top or config.top,
            min_size=minimum,
            max_depth=max_depth,
            exclude=(*config.exclude_patterns, *(exclude or ())),
            allow_root=allow_root,
            progress_event=progress_event,
        )

    try:
        minimum = parse_size(min_size)
        if scan_console.is_terminal and not json_output:
            scan_root = path.expanduser().resolve(strict=False)
            live_view = LiveScanView(
                ScanProgress(0, 0, 0, scan_root, 0.0),
                scan_root=scan_root,
            )
            live = Live(
                live_view,
                console=scan_console,
                transient=True,
                refresh_per_second=8,
            )
            live_started = False

            def update_live(progress: ScanProgress) -> None:
                nonlocal live_started
                live_view.update(progress)
                if not live_started:
                    live.start()
                    live_started = True

            try:
                result = run_scan(progress_event=update_live)
            finally:
                if live_started:
                    live.stop()
        else:
            result = run_scan()
    except (OSError, ValueError, RuntimeError) as exc:
        if json_output:
            typer.echo(f"Scan error: {exc}", err=True)
        else:
            render_scan_failure(path, exc, console=scan_console)
        raise typer.Exit(2) from exc
    if json_output:
        typer.echo(
            json.dumps(
                {
                    "root": str(result.root),
                    "status": "complete" if result.complete else "partial",
                    "files_visited": result.files_visited,
                    "directories_visited": result.directories_visited,
                    "errors": result.errors,
                    "duration_seconds": round(result.duration_seconds, 3),
                    "total_logical_bytes": result.total_logical_bytes,
                    "depth_limited": result.depth_limited,
                    "entries": [
                        {
                            "type": entry.entry_type,
                            "path": entry.relative_path,
                            "logical_bytes": entry.logical_bytes,
                            "allocated_bytes": entry.allocated_bytes,
                        }
                        for entry in result.top_entries
                    ],
                    "warnings": result.warnings,
                },
                indent=2,
            )
        )
    else:
        render_scan_results(result, console=scan_console)
    if not result.complete:
        raise typer.Exit(3)


@app.command()
def docker() -> None:
    """Show read-only Docker disk usage for the active Docker context."""
    if not _config().docker_enabled:
        console.print("Docker integration is disabled in DiskHawk configuration.")
        raise typer.Exit(4)
    result = get_docker_usage()
    console.print(f"Docker status: {result.state.replace('_', ' ')}")
    if result.context:
        console.print(f"Context: {result.context} (may be remote)")
    for category, values in result.categories.items():
        console.print(
            f"{category}: {format_bytes(values['size_bytes'])} total; "
            f"{format_bytes(values['reclaimable_bytes'])} reclaimable estimate"
        )
    for warning in result.warnings:
        console.print(f"Warning: {warning}")
    if result.state != "available":
        raise typer.Exit(4)


@app.command()
def ask(
    text: Annotated[list[str], typer.Argument(help="A supported local disk-related phrase.")],
) -> None:
    """Route a documented natural-language phrase without AI or network access."""
    phrase = " ".join(text)
    try:
        action = route_phrase(phrase)
    except ValueError:
        console.print("I don't recognize that request. Supported phrases:")
        for item in supported_phrases():
            console.print(f"  - {item}")
        raise typer.Exit(2) from None
    if action == Action.INFO:
        info()
    elif action == Action.SCAN:
        scan()
    elif action == Action.DOCKER:
        docker()


@app.command()
def report(
    output: Annotated[Path | None, typer.Option("--output", help="Report output path.")] = None,
    report_format: Annotated[
        str | None, typer.Option("--format", help="Report format: json or text.")
    ] = None,
    scan_path: Annotated[
        Path | None,
        typer.Option("--scan-path", help="Include aggregate scan results for this directory."),
    ] = None,
    include_details: Annotated[
        bool, typer.Option("--include-details", help="Include relative top filenames.")
    ] = False,
    yes_include_details: Annotated[
        bool,
        typer.Option(
            "--yes-include-details",
            help="Confirm detailed filename sharing in non-interactive use.",
        ),
    ] = False,
    include_docker: Annotated[
        bool, typer.Option("--docker", help="Include read-only Docker usage.")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing report.")] = False,
) -> None:
    """Create a sanitized local diagnostic report."""
    config = _config()
    if include_details and scan_path is None:
        typer.echo("--include-details requires --scan-path.", err=True)
        raise typer.Exit(2)
    if include_details:
        if not sys.stdin.isatty() and not yes_include_details:
            typer.echo("Non-interactive detailed reports require --yes-include-details.", err=True)
            raise typer.Exit(2)
        if sys.stdin.isatty() and not typer.confirm(
            "Include relative filenames and folder names in this report?"
        ):
            raise typer.Exit(2)
    chosen_format = report_format or config.report_format
    if chosen_format not in {"json", "text"}:
        typer.echo("--format must be json or text.", err=True)
        raise typer.Exit(2)
    filesystems = relevant_filesystems()
    docker_data = None
    if include_docker:
        if not config.docker_enabled:
            typer.echo("Docker integration is disabled in DiskHawk configuration.", err=True)
            raise typer.Exit(4)
        docker_result = get_docker_usage()
        docker_data = {
            "state": docker_result.state,
            "context": docker_result.context,
            "categories": docker_result.categories,
            "warnings": docker_result.warnings,
        }
    scan_result = None
    if scan_path is not None:
        try:
            scan_result = scan_directory(
                scan_path,
                top=config.top,
                exclude=config.exclude_patterns,
            )
        except (OSError, ValueError) as exc:
            typer.echo(f"Report scan failed: {exc}", err=True)
            raise typer.Exit(2) from exc
    report_data = build_report(
        filesystems,
        config,
        scan=scan_result,
        docker=docker_data,
        include_details=include_details,
    )
    content = render_json(report_data) if chosen_format == "json" else render_text(report_data)
    extension = "json" if chosen_format == "json" else "txt"
    target = output or Path(config.report_directory or Path.cwd()) / f"diskhawk-report.{extension}"
    if target.exists() and not force:
        if not sys.stdin.isatty() or not typer.confirm(f"{target} exists. Overwrite it?"):
            typer.echo(
                "Report not written: destination exists. Use --force to overwrite.",
                err=True,
            )
            raise typer.Exit(2)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + ("" if content.endswith("\n") else "\n"), encoding="utf-8")
    except OSError as exc:
        typer.echo(f"Could not write report: {exc}", err=True)
        raise typer.Exit(1) from exc
    console.print(f"Report saved: {target}")


@profile_app.command("show")
def profile_show() -> None:
    """Show active non-secret configuration settings."""
    console.print_json(json.dumps(_config().as_dict()))


@profile_app.command("export")
def profile_export(
    path: Annotated[Path, typer.Argument(help="Destination JSON profile.")] = Path(
        "diskhawk-profile.json"
    ),
) -> None:
    """Export a portable profile."""
    try:
        export_profile(path, _config())
    except (OSError, ValueError) as exc:
        typer.echo(f"Profile export failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    console.print(f"Profile exported: {path}")


@profile_app.command("import")
def profile_import(
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    yes: Annotated[
        bool, typer.Option("--yes", help="Confirm profile changes without an interactive prompt.")
    ] = False,
) -> None:
    """Preview and apply a validated profile."""
    try:
        imported = import_profile(path)
        current = _config()
    except (OSError, ValueError) as exc:
        typer.echo(f"Profile import failed: {exc}", err=True)
        raise typer.Exit(2) from exc
    console.print("Profile changes:")
    for key, new_value in imported.as_dict().items():
        old_value = current.as_dict().get(key)
        if old_value != new_value:
            console.print(f"  {key}: {old_value!r} -> {new_value!r}")
    if not yes and (not sys.stdin.isatty() or not typer.confirm("Apply these settings?")):
        console.print("Profile not applied.")
        raise typer.Exit(2)
    try:
        save_config(imported)
    except OSError as exc:
        typer.echo(f"Could not save configuration: {exc}", err=True)
        raise typer.Exit(1) from exc
    console.print("Profile applied.")


@shell_app.command("install")
def shell_install(
    shell: Annotated[str, typer.Argument(help="Supported shell: zsh or bash.")],
) -> None:
    """Back up and install the opt-in `give me disk info` shell function."""
    try:
        target_path = startup_file(shell)
        console.print(f"Will update shell startup file: {target_path}")
        target, backup = install_shell_integration(shell)
    except (OSError, ShellIntegrationError) as exc:
        typer.echo(f"Shell integration not installed: {exc}", err=True)
        raise typer.Exit(2) from exc
    console.print(f"Updated {target}; reopen the shell or source this file.")
    if backup:
        console.print(f"Backup: {backup}")


@shell_app.command("uninstall")
def shell_uninstall(
    shell: Annotated[str, typer.Argument(help="Supported shell: zsh or bash.")],
) -> None:
    """Back up and remove only the DiskHawk-managed shell block."""
    try:
        target_path = startup_file(shell)
        console.print(f"Will remove the managed block from: {target_path}")
        target, backup = uninstall_shell_integration(shell)
    except (OSError, ShellIntegrationError) as exc:
        typer.echo(f"Shell integration not removed: {exc}", err=True)
        raise typer.Exit(2) from exc
    console.print(f"Removed the DiskHawk block from {target}.")
    if backup:
        console.print(f"Backup: {backup}")


@app.command()
def ui() -> None:
    """Launch the interactive terminal user interface."""
    try:
        from diskhawk.tui.app import DiskHawkApp

        DiskHawkApp().run()
    except ImportError as exc:
        typer.echo(f"Textual TUI is unavailable: {exc}", err=True)
        raise typer.Exit(1) from exc
