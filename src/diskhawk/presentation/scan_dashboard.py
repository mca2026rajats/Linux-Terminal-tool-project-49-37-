from __future__ import annotations

import time
from pathlib import Path

from rich.align import Align
from rich.cells import cell_len
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from diskhawk.core.models import ScanSummary
from diskhawk.core.scanner import ScanProgress
from diskhawk.core.size_format import format_bytes

_MINT = "#03FDC7"
_WHITE = "#FFFFFF"
_PURPLE = "#A78BFA"
_CYAN = "#38BDF8"
_AMBER = "#FBBF24"
_CORAL = "#FF6B6B"
_DIM = "#514965"
_PANEL = "#252136"
_MAX_WIDTH = 100


def _width(console: Console) -> int:
    return min(console.width, _MAX_WIDTH)


def _scope_label(path: Path | str) -> str:
    try:
        return "FILESYSTEM ROOT" if Path(path).is_mount() else "DIRECTORY"
    except OSError:
        return "DIRECTORY"


def _path_text(path: Path | str, width: int, *, style: str) -> Text:
    value = str(path)
    if cell_len(value) <= width:
        return Text(value, style=style)
    parts = Path(value).parts
    if parts and cell_len(parts[-1]) + 4 > width:
        name = parts[-1]
        tail_width = min(max(4, width // 3), len(name))
        head_width = max(1, width - tail_width - 3)
        return Text(f"{name[:head_width]}...{name[-tail_width:]}", style=style)
    suffix_parts: list[str] = []
    for part in reversed(parts):
        candidate = ".../" + "/".join(reversed([*suffix_parts, part]))
        if cell_len(candidate) > width:
            break
        suffix_parts.append(part)
    shortened = ".../" + "/".join(reversed(suffix_parts)) if suffix_parts else value
    text = Text(shortened, style=style)
    text.truncate(width, overflow="ellipsis")
    return text


def _pixel_line(console: Console, frame: int) -> Text:
    width = max(8, min(32, _width(console) - 48))
    phase = frame % (width * 2 - 2)
    position = phase if phase < width else 2 * width - phase - 2
    if "utf" in console.encoding.casefold():
        background, beam = "░", "█"
    else:
        background, beam = ".", "#"
    text = Text(background * position + beam + background * (width - position - 1), style=_DIM)
    text.stylize(f"bold {_MINT}", position, position + 1)
    return text


def scanning_view(
    progress: ScanProgress,
    *,
    scan_root: Path,
    console: Console,
    frame: int,
) -> Panel:
    width = _width(console)
    scope = _scope_label(scan_root)
    pixel_art = Group(
        Text("  +-----------------+", style=f"bold {_MINT}"),
        Text("  |  DISKHAWK SCAN  |", style=_MINT),
        Text("  |   [  PIXEL  ]   |", style=f"bold {_MINT}"),
        Text("  +--------+--------+", style=f"bold {_MINT}"),
        Align.center(_pixel_line(console, frame)),
    )
    heading = Text()
    heading.append("DISKHAWK", style=f"bold {_MINT}")
    heading.append(f"  /  {scope} SCANNER", style=f"bold {_WHITE}")

    stats = Table.grid(expand=True, padding=(0, 1))
    stats.add_column(ratio=1)
    stats.add_column(ratio=1)
    stats.add_column(ratio=1)
    stats.add_row(
        _stat("FILES", str(progress.files_visited), _CYAN),
        _stat("DIRECTORIES", str(progress.directories_visited), _CYAN),
        _stat("INACCESSIBLE", str(progress.errors), _AMBER if progress.errors else _CYAN),
    )
    path = _path_text(progress.current_path, max(12, width - 18), style=_PURPLE)
    content = Group(
        Align.center(pixel_art),
        Align.center(Text("SCANNING  ·  NO COMPLETION ESTIMATE", style=f"bold {_MINT}")),
        stats,
        Text(f"ELAPSED  {progress.elapsed_seconds:.1f} s", style=_CYAN),
        Text("CURRENT PATH", style=f"bold {_PURPLE}"),
        path,
    )
    return Panel(
        content,
        title=heading,
        title_align="left",
        border_style=_MINT,
        padding=(0, 1),
        width=width,
        style=f"on {_PANEL}",
    )


class LiveScanView:
    def __init__(self, progress: ScanProgress, *, scan_root: Path) -> None:
        self.progress = progress
        self.scan_root = scan_root
        self.started_at = time.monotonic()
        self.updated_at = self.started_at

    def update(self, progress: ScanProgress) -> None:
        self.progress = progress
        self.updated_at = time.monotonic()

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        now = time.monotonic()
        frame = int((now - self.started_at) * 8)
        progress = ScanProgress(
            files_visited=self.progress.files_visited,
            directories_visited=self.progress.directories_visited,
            errors=self.progress.errors,
            current_path=self.progress.current_path,
            elapsed_seconds=(self.progress.elapsed_seconds + max(0.0, now - self.updated_at)),
        )
        yield scanning_view(
            progress,
            scan_root=self.scan_root,
            console=console,
            frame=frame,
        )


def _stat(label: str, value: str, color: str) -> Group:
    return Group(Text(label, style=f"bold {_PURPLE}"), Text(value, style=f"bold {color}"))


def _status(summary: ScanSummary) -> tuple[str, str]:
    warning_text = " ".join(summary.warnings).casefold()
    if "interrupted" in warning_text or "cancelled" in warning_text:
        return "SCAN INTERRUPTED", _AMBER
    if summary.root_error:
        return "SCAN FAILED", _CORAL
    if summary.complete:
        return "SCAN COMPLETE", _MINT
    return "SCAN COMPLETE WITH WARNINGS", _AMBER


def _entry_bar(logical_bytes: int, maximum: int, width: int, console: Console) -> Text:
    filled = round(logical_bytes / maximum * width) if maximum else 0
    if "utf" in console.encoding.casefold():
        full, empty = "█", "░"
    else:
        full, empty = "#", "."
    bar = Text(full * filled, style=f"bold {_MINT}")
    bar.append(empty * (width - filled), style=_DIM)
    return bar


def render_scan_results(summary: ScanSummary, *, console: Console) -> None:
    width = _width(console)
    scope = _scope_label(summary.root)
    status, status_color = _status(summary)
    status_text = Text(status, style=f"bold {status_color}")
    root = _path_text(summary.root, max(12, width - 24), style=_PURPLE)

    summary_grid = Table.grid(expand=True, padding=(0, 1))
    summary_grid.add_column(ratio=1)
    summary_grid.add_column(ratio=1)
    summary_grid.add_column(ratio=1)
    summary_grid.add_row(
        _stat("FILES INSPECTED", str(summary.files_visited), _WHITE),
        _stat("DIRECTORIES", str(summary.directories_visited), _WHITE),
        _stat("INACCESSIBLE", str(summary.errors), _AMBER if summary.errors else _WHITE),
    )
    summary_grid.add_row(
        _stat("LOGICAL FILE SIZE", format_bytes(summary.total_logical_bytes), _WHITE),
        _stat("DURATION", f"{summary.duration_seconds:.2f} s", _WHITE),
        _stat("WARNINGS", str(len(summary.warnings)), _AMBER if summary.warnings else _WHITE),
    )
    console.print(
        Panel(
            Group(
                status_text,
                Text("SCAN ROOT", style=f"bold {_PURPLE}"),
                root,
                summary_grid,
            ),
            title=Text(f"DISKHAWK  /  {scope} SCAN SUMMARY", style=f"bold {_WHITE}"),
            title_align="left",
            border_style=status_color,
            padding=(0, 1),
            width=width,
            style=f"on {_PANEL}",
        ),
        width=width,
    )

    entries = sorted(
        summary.top_entries,
        key=lambda item: (-item.logical_bytes, item.relative_path.casefold()),
    )
    if entries:
        bar_width = max(8, min(16, (width - 64) // 2))
        table = Table(
            title="LARGEST SPACE CONSUMERS",
            expand=True,
            box=None,
            pad_edge=False,
            padding=(0, 1),
            title_style=f"bold {_CYAN}",
        )
        table.add_column("TYPE", style=_CYAN, no_wrap=True, width=6)
        table.add_column("PATH", style=_PURPLE, ratio=1, no_wrap=True, overflow="ellipsis")
        table.add_column("LOGICAL", style=_WHITE, justify="right", no_wrap=True)
        table.add_column("ALLOC EST.", style=_PURPLE, justify="right", no_wrap=True)
        table.add_column("SIZE MAP", no_wrap=True, width=bar_width)
        maximum = max(entry.logical_bytes for entry in entries)
        for entry in entries:
            table.add_row(
                "DIR" if entry.entry_type == "directory" else "FILE",
                _path_text(entry.relative_path, max(12, width - 56), style=_PURPLE),
                format_bytes(entry.logical_bytes),
                format_bytes(entry.allocated_bytes),
                _entry_bar(entry.logical_bytes, maximum, bar_width, console),
            )
        console.print(
            Panel(
                table,
                border_style=_DIM,
                padding=(0, 1),
                width=width,
                style=f"on {_PANEL}",
            ),
            width=width,
        )
    else:
        console.print(
            Panel(
                Text("No files or directories matched the scan filters.", style=_CYAN),
                title="LARGEST SPACE CONSUMERS",
                border_style=_DIM,
                padding=(0, 1),
                width=width,
            ),
            width=width,
        )

    console.print(
        Text(
            "Directory logical sizes and allocated-byte values are estimates; "
            "they are not guaranteed reclaimable space.",
            style=_CYAN,
        ),
        width=width,
    )
    for warning in summary.warnings:
        console.print(Text(f"WARNING  {warning}", style=_AMBER), width=width)


def render_scan_failure(
    path: Path | str,
    error: Exception,
    *,
    console: Console,
) -> None:
    width = _width(console)
    scope = _scope_label(path)
    root = _path_text(path, max(12, width - 24), style=_PURPLE)
    detail = Text(str(error), style=_WHITE)
    detail.truncate(max(12, width - 8), overflow="ellipsis")
    content: RenderableType = Group(
        Text("SCAN FAILED", style=f"bold {_CORAL}"),
        Text("SCAN ROOT", style=f"bold {_PURPLE}"),
        root,
        detail,
    )
    console.print(
        Panel(
            content,
            title=f"DISKHAWK  /  {scope} SCANNER",
            border_style=_CORAL,
            padding=(0, 1),
            width=width,
            style=f"on {_PANEL}",
        ),
        width=width,
    )
