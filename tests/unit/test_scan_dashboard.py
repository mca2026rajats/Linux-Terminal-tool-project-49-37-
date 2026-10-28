from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from rich.cells import cell_len
from rich.console import Console

from diskhawk.core.models import ScanEntry, ScanSummary
from diskhawk.core.scanner import ScanProgress
from diskhawk.presentation import scan_dashboard
from diskhawk.presentation.scan_dashboard import (
    LiveScanView,
    render_scan_failure,
    render_scan_results,
)


def _summary(
    root: Path,
    *,
    complete: bool = True,
    warnings: tuple[str, ...] = (),
    entries: tuple[ScanEntry, ...] | None = None,
    root_error: bool = False,
) -> ScanSummary:
    now = datetime.now(UTC)
    return ScanSummary(
        root=root,
        started_at=now,
        completed_at=now,
        duration_seconds=1.25,
        files_visited=2,
        directories_visited=2,
        errors=0,
        complete=complete,
        depth_limited=False,
        total_logical_bytes=300,
        top_entries=(
            entries
            if entries is not None
            else (
                ScanEntry("nested", "directory", 200, 256, 1),
                ScanEntry("nested/big file.bin", "file", 200, 256, 2),
                ScanEntry("small.txt", "file", 100, 512, 1),
            )
        ),
        warnings=warnings,
        root_error=root_error,
    )


def _console(width: int = 100, encoding: str = "utf-8") -> tuple[Console, StringIO]:
    class Output(StringIO):
        @property
        def encoding(self) -> str:
            return encoding

    output = Output()
    return Console(file=output, width=width, no_color=True), output


@pytest.mark.parametrize("width", [80, 100, 120])
def test_scan_results_fit_supported_widths_and_show_real_summary(
    tmp_path: Path, width: int
) -> None:
    console, output = _console(width)
    summary = _summary(tmp_path)
    render_scan_results(summary, console=console)
    rendered = output.getvalue()
    assert max(cell_len(line) for line in rendered.splitlines()) <= min(width, 100)
    assert "SCAN COMPLETE" in rendered
    assert tmp_path.name in rendered
    assert "2" in rendered
    assert "300 B" in rendered
    assert "1.25 s" in rendered
    assert "nested/big file.bin" in rendered
    assert "LOGICAL" in rendered
    assert "ALLOC EST." in rendered
    assert "not guaranteed reclaimable space" in " ".join(rendered.split())


def test_scan_results_sort_largest_items_and_render_bars(tmp_path: Path) -> None:
    console, output = _console(100)
    summary = _summary(
        tmp_path,
        entries=(
            ScanEntry("small", "file", 1, None, 1),
            ScanEntry("large", "directory", 10_000, 10_240, 1),
            ScanEntry("medium", "file", 1000, 1024, 1),
        ),
    )
    render_scan_results(summary, console=console)
    rendered = output.getvalue()
    assert rendered.index("large") < rendered.index("medium") < rendered.index("small")
    assert "██████████████" in rendered


@pytest.mark.parametrize("width", [80, 100, 120])
def test_scan_results_keep_long_filename_bounded(tmp_path: Path, width: int) -> None:
    filename = "unusually-long-artifact-name-" + "x" * 100 + ".bin"
    console, output = _console(width)
    render_scan_results(
        _summary(
            tmp_path,
            entries=(ScanEntry(filename, "file", 100, 128, 1),),
        ),
        console=console,
    )
    rendered = output.getvalue()
    assert max(cell_len(line) for line in rendered.splitlines()) <= min(width, 100)
    assert "unusually" in rendered
    assert ".bin" in rendered


def test_scan_results_distinguish_warnings_and_interruption(tmp_path: Path) -> None:
    console, output = _console()
    render_scan_results(
        _summary(tmp_path, complete=False, warnings=("One path was inaccessible.",)),
        console=console,
    )
    assert "SCAN COMPLETE WITH WARNINGS" in output.getvalue()

    console, output = _console()
    render_scan_results(
        _summary(tmp_path, complete=False, warnings=("Scan interrupted by user.",)),
        console=console,
    )
    assert "SCAN INTERRUPTED" in output.getvalue()


def test_scan_results_identify_filesystem_root_scans() -> None:
    console, output = _console()
    render_scan_results(_summary(Path("/")), console=console)
    assert "FILESYSTEM ROOT SCAN SUMMARY" in output.getvalue()


def test_scan_results_distinguish_root_failure(tmp_path: Path) -> None:
    console, output = _console()
    render_scan_results(_summary(tmp_path, complete=False, root_error=True), console=console)
    assert "SCAN FAILED" in output.getvalue()


def test_scan_results_handle_empty_results_and_ascii_terminal(tmp_path: Path) -> None:
    console, output = _console(80, "ascii")
    render_scan_results(_summary(tmp_path, entries=()), console=console)
    rendered = output.getvalue()
    assert "No files or directories matched" in rendered
    assert "█" not in rendered
    assert "░" not in rendered


def test_scan_failure_is_reported_without_claiming_success(tmp_path: Path) -> None:
    console, output = _console(80)
    render_scan_failure(
        tmp_path / "not-a-directory", ValueError("not a directory"), console=console
    )
    rendered = output.getvalue()
    assert "SCAN FAILED" in rendered
    assert "not a directory" in rendered
    assert "SCAN COMPLETE" not in rendered


def test_live_scan_view_renders_indeterminate_status_and_progress(tmp_path: Path) -> None:
    progress = ScanProgress(25, 4, 1, tmp_path / "somewhere", 3.5)
    console, output = _console(80)
    view = LiveScanView(progress, scan_root=tmp_path)
    console.print(view)
    rendered = output.getvalue()
    assert "SCANNING" in rendered
    assert "DIRECTORY SCANNER" in rendered
    assert "NO COMPLETION ESTIMATE" in rendered
    assert "%" not in rendered
    assert "25" in rendered
    assert "4" in rendered
    assert "1" in rendered
    assert tmp_path.name in rendered
    assert "somewhere" in rendered

    updated = ScanProgress(26, 4, 1, tmp_path / "next", 3.6)
    view.update(updated)
    console, output = _console(80)
    console.print(view)
    assert "next" in output.getvalue()


def test_live_scan_elapsed_time_advances_between_scanner_events(
    tmp_path: Path, monkeypatch
) -> None:
    ticks = iter((10.0, 12.0, 15.0))
    monkeypatch.setattr(scan_dashboard.time, "monotonic", lambda: next(ticks))
    view = LiveScanView(
        ScanProgress(0, 0, 0, tmp_path, 0.0),
        scan_root=tmp_path,
    )
    view.update(ScanProgress(1, 1, 0, tmp_path / "large", 4.0))
    console, output = _console()
    console.print(view)
    assert "ELAPSED  7.0 s" in output.getvalue()
