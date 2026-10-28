from __future__ import annotations

import os
from pathlib import PurePosixPath
from typing import TextIO

from rich import box
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from diskhawk import __version__
from diskhawk.core.disk_activity import DiskActivity
from diskhawk.core.models import FilesystemInfo
from diskhawk.core.size_format import format_bytes
from diskhawk.theme import THEME

_MINT = "#03FDC7"
_WHITE = "#FFFFFF"
_PURPLE = "#A78BFA"
_BACKGROUND = "#17151F"
_PANEL = "#252136"
_DIM = "#514965"
_CORAL = "#FF6B6B"

_PIXEL_DRIVE = "  +-------------+\n  | [#] DISK     |\n  |   [====]    |\n  +-------------+"


def storage_segments(used_percent: float, *, width: int = 20) -> tuple[str, str]:
    if width < 1:
        raise ValueError("Storage bar width must be positive.")
    if not 0 <= used_percent <= 100:
        raise ValueError("Storage percentage must be between 0 and 100.")
    filled = min(width, int(used_percent * width / 100))
    return "█" * filled, "░" * (width - filled)


def _storage_bar_characters(console: Console) -> tuple[str, str]:
    if "utf" in console.encoding.casefold():
        return "█", "░"
    return "#", "."


def _panel_box(console: Console) -> box.Box:
    return box.ROUNDED if "utf" in console.encoding.casefold() else box.ASCII


def _validate_filesystem(item: FilesystemInfo) -> None:
    if item.total_bytes <= 0:
        raise ValueError(f"Filesystem {item.mount_point!r} has no valid capacity data.")
    if not 0 <= item.used_bytes <= item.total_bytes:
        raise ValueError(f"Filesystem {item.mount_point!r} has invalid used-space data.")
    if not 0 <= item.available_bytes <= item.total_bytes:
        raise ValueError(f"Filesystem {item.mount_point!r} has invalid available-space data.")
    if item.used_bytes + item.available_bytes > item.total_bytes:
        raise ValueError(f"Filesystem {item.mount_point!r} has inconsistent capacity data.")


def _volume_name(item: FilesystemInfo) -> str:
    if item.source:
        name = PurePosixPath(item.source.rstrip("/")).name
        if name:
            return name
    mount_name = PurePosixPath(item.mount_point.rstrip("/")).name
    return mount_name or item.mount_point


def _header(console: Console) -> RenderableType:
    separator = "  ·  " if "utf" in console.encoding.casefold() else "  |  "
    title = Text()
    title.append("DISKHAWK", style=f"bold {_MINT}")
    title.append(f"{separator}PIXEL STORAGE TERMINAL", style=_WHITE)
    title.append(f"\nv{__version__}  /  LOCAL CAPACITY VIEW", style=_PURPLE)
    if console.width >= 58:
        header = Table.grid(expand=True, padding=(0, 1))
        header.add_column(width=19, no_wrap=True)
        header.add_column(ratio=1)
        header.add_row(Text(_PIXEL_DRIVE, style=f"bold {_MINT}"), title)
        return Panel(
            header,
            border_style=_MINT,
            padding=(0, 1),
            box=_panel_box(console),
            style=f"on {_BACKGROUND}",
            width=min(console.width, 100),
        )
    return Panel(
        Group(Text(_PIXEL_DRIVE, style=f"bold {_MINT}"), title),
        border_style=_MINT,
        padding=(0, 1),
        box=_panel_box(console),
        style=f"on {_BACKGROUND}",
    )


def _metric_panel(
    label: str,
    amount: str,
    percent: str,
    *,
    console: Console,
    warning: bool = False,
) -> Panel:
    value = Text(amount, style=f"bold {_CORAL if warning else _WHITE}")
    value.append(f"\n{percent}", style=_PURPLE)
    return Panel(
        value,
        title=Text(label, style=f"bold {_PURPLE}"),
        title_align="left",
        border_style=_CORAL if warning else _DIM,
        padding=(0, 1),
        box=_panel_box(console),
        style=f"on {_PANEL}",
    )


def _format_throughput(bytes_per_second: float | None) -> str:
    if bytes_per_second is None:
        return "N/A"
    if bytes_per_second == 0:
        return "0.00 MB/s"
    if bytes_per_second >= 1_000_000:
        return f"{bytes_per_second / 1_000_000:.2f} MB/s"
    kilobytes_per_second = bytes_per_second / 1_000
    if round(kilobytes_per_second, 2) == 0:
        return "<0.01 KB/s"
    return f"{kilobytes_per_second:.2f} KB/s"


def _activity_panel(activity: DiskActivity, console: Console) -> Panel:
    readings = Table.grid(expand=True, padding=(0, 1))
    readings.add_column(width=14, no_wrap=True)
    readings.add_column(ratio=1, justify="right", no_wrap=True)
    readings.add_row(
        Text("READ SPEED", style=f"bold {_MINT}"),
        Text(_format_throughput(activity.read_bytes_per_second), style=f"bold {_WHITE}"),
    )
    readings.add_row(
        Text("WRITE SPEED", style=f"bold {_PURPLE}"),
        Text(_format_throughput(activity.write_bytes_per_second), style=f"bold {_WHITE}"),
    )
    return Panel(
        Group(readings, Text(activity.status, style=_PURPLE)),
        title=Text("LIVE DISK ACTIVITY", style=f"bold {_WHITE}"),
        title_align="left",
        border_style=_DIM,
        padding=(0, 1),
        box=_panel_box(console),
        style=f"on {_PANEL}",
        width=min(console.width, 100),
    )


def _filesystem_panel(item: FilesystemInfo, threshold: int, console: Console) -> Panel:
    _validate_filesystem(item)
    used_percent = item.used_bytes / item.total_bytes * 100
    available_percent = item.available_bytes / item.total_bytes * 100
    bar_width = max(8, min(32, console.width - 54))
    filled, empty = storage_segments(used_percent, width=bar_width)
    used_char, available_char = _storage_bar_characters(console)

    details = Table.grid(expand=True, padding=(0, 1))
    details.add_column(width=8, no_wrap=True)
    details.add_column(ratio=1)
    details.add_row(Text("VOLUME", style=f"bold {_PURPLE}"), Text(_volume_name(item), style=_WHITE))
    details.add_row(Text("MOUNT", style=f"bold {_PURPLE}"), Text(item.mount_point, style=_WHITE))

    bar = Text()
    bar.append(filled.replace("█", used_char), style=f"bold {_MINT}")
    bar.append(empty.replace("░", available_char), style=_PURPLE)
    bar_row = Table.grid(expand=True, padding=(0, 1))
    bar_row.add_column(ratio=1)
    bar_row.add_column(no_wrap=True, justify="right")
    bar_row.add_row(bar, Text(f"{used_percent:.1f}% used", style=_WHITE))
    legend = Text()
    legend.append(f"{used_char * 2} ", style=f"bold {_MINT}")
    legend.append("USED", style=_MINT)
    legend.append("    ")
    legend.append(f"{available_char * 2} ", style=f"bold {_PURPLE}")
    legend.append("AVAILABLE", style=_PURPLE)

    warning = used_percent >= threshold
    metrics = [
        _metric_panel(
            "SPACE USED",
            format_bytes(item.used_bytes),
            f"{used_percent:.1f}% of capacity",
            console=console,
            warning=warning,
        ),
        _metric_panel(
            "SPACE FREE",
            format_bytes(item.available_bytes),
            f"{available_percent:.1f}% available",
            console=console,
        ),
        _metric_panel(
            "TOTAL CAPACITY",
            format_bytes(item.total_bytes),
            "filesystem capacity",
            console=console,
        ),
    ]
    metric_row: RenderableType
    if console.width >= 80:
        metric_row = Columns(metrics, equal=True, expand=True, padding=(0, 1))
    else:
        metric_row = Group(*metrics)

    body = Group(
        details,
        Text("STORAGE MAP", style=f"bold {_PURPLE}"),
        bar_row,
        legend,
        metric_row,
    )
    heading = Text("FILESYSTEM CAPACITY", style=f"bold {_PURPLE}")
    return Panel(
        body,
        title=heading,
        title_align="left",
        border_style=_DIM,
        padding=(0, 1),
        box=_panel_box(console),
        style=f"on {_PANEL}",
        width=min(console.width, 100),
    )


def render_pixel_disk_info(
    filesystems: list[FilesystemInfo],
    *,
    console: Console,
    warning_threshold_percent: int = 90,
    view_note: str | None = None,
    activity: DiskActivity | None = None,
) -> None:
    """Render a pixel dashboard from previously collected filesystem and activity data."""
    if not filesystems:
        raise ValueError("No supported filesystem capacity data was found.")
    if not 1 <= warning_threshold_percent <= 100:
        raise ValueError("Warning threshold must be between 1 and 100.")
    for item in filesystems:
        _validate_filesystem(item)

    render_width = min(console.width, 100)
    render_console = console
    render_console.print(_header(render_console), width=render_width)
    if view_note:
        note = Text(view_note, style=_PURPLE)
        render_console.print(
            Panel(note, border_style=_DIM, padding=(0, 1), width=render_width),
            width=render_width,
        )
    for item in filesystems:
        render_console.print(
            _filesystem_panel(item, warning_threshold_percent, render_console),
            width=render_width,
        )
        if item.used_bytes / item.total_bytes * 100 >= warning_threshold_percent:
            warning = Text(
                f"{item.mount_point} is at or above the configured "
                f"{warning_threshold_percent}% threshold.",
                style=_WHITE,
            )
            render_console.print(
                Panel(
                    warning,
                    title=Text("CAPACITY WARNING", style=f"bold {_CORAL}"),
                    title_align="left",
                    border_style=_CORAL,
                    padding=(0, 1),
                    box=_panel_box(render_console),
                    style=f"on {_PANEL}",
                    width=render_width,
                ),
                width=render_width,
            )

    render_console.print(
        _activity_panel(
            activity or DiskActivity(None, None, "N/A: live activity sampling was not performed"),
            render_console,
        ),
        width=render_width,
    )

    footer = Text()
    footer.append("CAPACITY READ COMPLETE", style=f"bold {_MINT}")
    separator = "  ·  " if "utf" in console.encoding.casefold() else "  |  "
    footer.append(f"{separator}READ-ONLY{separator}", style=_PURPLE)
    footer.append("HARDWARE HEALTH NOT ASSESSED", style=_WHITE)
    render_console.print(
        Panel(
            footer,
            border_style=_MINT,
            padding=(0, 1),
            box=_panel_box(console),
            style=f"on {_BACKGROUND}",
            width=render_width,
        ),
        width=render_width,
    )


def dashboard_console(
    *,
    file: TextIO,
    color: str,
) -> Console:
    """Create an info-only console that respects TTY, NO_COLOR, and TERM=dumb."""
    no_color = color == "never" or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb"
    force_terminal = color == "always" and not no_color and file.isatty()
    return Console(
        file=file,
        theme=THEME,
        force_terminal=force_terminal if force_terminal else None,
        no_color=no_color,
    )
