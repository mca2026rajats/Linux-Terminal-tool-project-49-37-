from __future__ import annotations

from io import StringIO

import pytest
from rich.cells import cell_len
from rich.console import Console

from diskhawk.core.disk_activity import DiskActivity
from diskhawk.core.models import FilesystemInfo
from diskhawk.presentation.pixel_dashboard import (
    _activity_panel,
    _filesystem_panel,
    _format_throughput,
    dashboard_console,
    render_pixel_disk_info,
    storage_segments,
)


def _filesystem(
    *,
    source: str | None = "/dev/disk3s5",
    mount: str = "/System/Volumes/Data",
    total: int = 100 * 1024**3,
    used: int = 37 * 1024**3,
    available: int = 60 * 1024**3,
) -> FilesystemInfo:
    return FilesystemInfo(
        mount_point=mount,
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        usage_percent=used / total * 100 if total else 0,
        source=source,
    )


def _render(
    item: FilesystemInfo,
    *,
    width: int = 100,
    encoding: str = "utf-8",
    activity: DiskActivity | None = None,
) -> str:
    class Output(StringIO):
        @property
        def encoding(self) -> str:
            return encoding

    output = Output()
    console = Console(file=output, width=width, no_color=True)
    render_pixel_disk_info([item], console=console, activity=activity)
    return output.getvalue()


def test_storage_segments_match_usage_percentage() -> None:
    assert storage_segments(0, width=8) == ("", "░" * 8)
    assert storage_segments(37.5, width=8) == ("█" * 3, "░" * 5)
    assert storage_segments(100, width=8) == ("█" * 8, "")
    with pytest.raises(ValueError):
        storage_segments(25, width=0)
    with pytest.raises(ValueError):
        storage_segments(101)


def test_dashboard_renders_volume_mount_and_storage_statistics() -> None:
    output = _render(_filesystem())
    assert "DISKHAWK" in output
    assert "PIXEL STORAGE TERMINAL" in output
    assert "disk3s5" in output
    assert "/System/Volumes/Data" in output
    assert "SPACE USED" in output
    assert "37.0 GiB" in output
    assert "37.0% of capacity" in output
    assert "SPACE FREE" in output
    assert "60.0 GiB" in output
    assert "60.0% available" in output
    assert "TOTAL CAPACITY" in output
    assert "100.0 GiB" in output
    assert "DISK SCAN" not in output
    assert "CAPACITY READ COMPLETE" in output
    assert "READ-ONLY" in output
    assert "HARDWARE HEALTH NOT ASSESSED" in output
    assert "LIVE DISK ACTIVITY" in output
    assert "READ SPEED" in output
    assert "WRITE SPEED" in output
    assert "N/A" in output
    assert "healthy" not in output.lower()


def test_dashboard_is_readable_at_narrow_width() -> None:
    output = _render(_filesystem(mount="/Volumes/External Storage"), width=36)
    for label in ("DISKHAWK", "SPACE USED", "SPACE FREE", "TOTAL CAPACITY"):
        assert label in output
    assert all(part in output for part in ("/Volumes/External", "Storage"))
    assert max(cell_len(line) for line in output.splitlines()) <= 36


@pytest.mark.parametrize("width", [80, 100, 120])
def test_dashboard_alignment_at_supported_terminal_widths(width: int) -> None:
    item = _filesystem(
        source="/dev/disk-this-is-a-deliberately-long-volume-identifier-123456789",
        mount="/Volumes/External Storage With A Deliberately Long Mount Path",
        total=12 * 1024**4,
        used=11 * 1024**4 + 900 * 1024**3,
        available=124 * 1024**3,
    )
    output = _render(item, width=width)
    assert max(cell_len(line) for line in output.splitlines()) <= min(width, 100)
    normalized = " ".join(output.split())
    assert "disk-this-is-a-deliberately-long-volume-identifier-123456789" in normalized
    assert all(
        part in output
        for part in (
            "Volumes",
            "External",
            "Storage",
            "With",
            "Deliberately",
            "Long",
            "Mount",
            "Path",
        )
    )
    assert "99.0% used" in normalized
    assert "USED" in output
    assert "AVAILABLE" in output
    assert "CAPACITY WARNING" in output


@pytest.mark.parametrize("width", [80, 100, 120])
def test_activity_panel_aligns_with_dashboard_at_supported_widths(width: int) -> None:
    output = _render(
        _filesystem(),
        width=width,
        activity=DiskActivity(
            12_450_000,
            850_000,
            "Physical-device throughput measured over 1.00 s; not benchmark performance.",
        ),
    )
    assert max(cell_len(line) for line in output.splitlines()) <= min(width, 100)
    assert "12.45 MB/s" in output
    assert "850.00 KB/s" in output
    assert "measured over 1.00 s" in output
    assert "not benchmark performance" in output


def test_activity_labels_use_mint_and_purple() -> None:
    console = Console(
        file=StringIO(),
        width=100,
        force_terminal=True,
        color_system="truecolor",
    )
    panel = _activity_panel(
        DiskActivity(1_000_000, 2_000_000, "Measured over 1.00 s."),
        console,
    )
    segments = console.render(panel, console.options)
    read_segment = next(segment for segment in segments if "READ SPEED" in segment.text)
    write_segment = next(segment for segment in segments if "WRITE SPEED" in segment.text)
    read_color = read_segment.style.color.get_truecolor()
    write_color = write_segment.style.color.get_truecolor()
    assert (read_color.red, read_color.green, read_color.blue) == (3, 253, 199)
    assert (write_color.red, write_color.green, write_color.blue) == (167, 139, 250)


def test_throughput_formatting_uses_units_and_preserves_no_activity() -> None:
    assert _format_throughput(None) == "N/A"
    assert _format_throughput(0) == "0.00 MB/s"
    assert _format_throughput(12_450_000) == "12.45 MB/s"
    assert _format_throughput(12_500) == "12.50 KB/s"
    assert _format_throughput(1) == "<0.01 KB/s"
    assert _format_throughput(10**15) == "1000000000.00 MB/s"


def test_fully_used_filesystem_has_no_available_bar_segments() -> None:
    output = _render(_filesystem(total=100, used=100, available=0))
    assert "████████████████████" in output
    assert "100.0% used" in output
    assert "0 B" in output
    bar_row = next(line for line in output.splitlines() if "% used" in line)
    assert "░" not in bar_row


def test_dashboard_falls_back_to_ascii_for_ascii_terminal() -> None:
    output = _render(_filesystem(), encoding="ascii")
    assert "#" in output
    assert "." in output
    assert "█" not in output
    assert "░" not in output


def test_dashboard_has_no_ansi_for_redirected_output() -> None:
    output = _render(_filesystem())
    assert "\x1b[" not in output


def test_dashboard_uses_specified_foreground_palette_without_background() -> None:
    output = StringIO()
    console = Console(
        file=output,
        width=100,
        force_terminal=True,
        color_system="truecolor",
    )
    render_pixel_disk_info([_filesystem()], console=console)
    rendered = output.getvalue()
    assert "38;2;3;253;199" in rendered
    assert "38;2;167;139;250" in rendered
    assert "38;2;255;255;255" in rendered
    assert "48;2;23;21;31" in rendered
    assert "48;2;37;33;54" in rendered


def test_storage_bar_maps_used_to_mint_and_available_to_purple() -> None:
    console = Console(
        file=StringIO(),
        width=100,
        force_terminal=True,
        color_system="truecolor",
    )
    panel = _filesystem_panel(
        _filesystem(used=50 * 1024**3, available=50 * 1024**3),
        90,
        console,
    )
    segments = console.render(panel, console.options)
    used = next(segment for segment in segments if segment.text == "█" * 16)
    available = next(segment for segment in segments if segment.text == "░" * 16)
    used_color = used.style.color.get_truecolor()
    available_color = available.style.color.get_truecolor()
    assert (used_color.red, used_color.green, used_color.blue) == (3, 253, 199)
    assert (available_color.red, available_color.green, available_color.blue) == (167, 139, 250)


def test_dashboard_console_respects_no_color_and_term_dumb(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    color_console = dashboard_console(file=StringIO(), color="always")
    assert color_console.no_color
    assert not color_console.is_terminal
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    dumb_console = dashboard_console(file=StringIO(), color="auto")
    assert dumb_console.no_color
    monkeypatch.setenv("TERM", "xterm-256color")
    redirected = StringIO()
    redirected_console = dashboard_console(file=redirected, color="always")
    render_pixel_disk_info([_filesystem()], console=redirected_console)
    assert "\x1b[" not in redirected.getvalue()


def test_dashboard_rejects_missing_or_invalid_capacity_data() -> None:
    console = Console(file=StringIO(), width=80, no_color=True)
    with pytest.raises(ValueError, match="No supported filesystem"):
        render_pixel_disk_info([], console=console)
    with pytest.raises(ValueError, match="no valid capacity"):
        render_pixel_disk_info([_filesystem(total=0, used=0, available=0)], console=console)
    with pytest.raises(ValueError, match="invalid used-space"):
        render_pixel_disk_info([_filesystem(used=-1)], console=console)
    with pytest.raises(ValueError, match="invalid available-space"):
        render_pixel_disk_info([_filesystem(available=101 * 1024**3)], console=console)


def test_dashboard_handles_volume_without_source() -> None:
    output = _render(_filesystem(source=None, mount="/Volumes/Archive"))
    assert "Archive" in output
    assert "/Volumes/Archive" in output
