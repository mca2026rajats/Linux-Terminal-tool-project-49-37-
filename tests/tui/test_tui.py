from __future__ import annotations

import asyncio
import threading
import time
from datetime import UTC, datetime

from diskhawk.core.models import DiskHawkConfig, FilesystemInfo, ScanEntry, ScanSummary
from diskhawk.tui.app import DiskHawkApp


def _scan_summary(root) -> ScanSummary:
    now = datetime.now(UTC)
    return ScanSummary(
        root=root,
        started_at=now,
        completed_at=now,
        duration_seconds=0,
        files_visited=1,
        directories_visited=1,
        errors=0,
        complete=True,
        depth_limited=False,
        total_logical_bytes=12,
        top_entries=(ScanEntry("item.txt", "file", 12, 12, 1),),
    )


def test_tui_starts_and_help_modal_opens(monkeypatch) -> None:
    monkeypatch.setattr(
        "diskhawk.tui.app.relevant_filesystems",
        lambda: [FilesystemInfo("/", 100, 50, 50, 50)],
    )

    async def run() -> None:
        app = DiskHawkApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            assert app.query_one("#filesystems")
            await pilot.press("question_mark")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "MessageScreen"
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is app.screen_stack[0]
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is app.screen_stack[0]

    asyncio.run(run())


def test_tui_search_sort_and_refresh(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diskhawk.tui.app.load_config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.tui.app.relevant_filesystems",
        lambda: [
            FilesystemInfo("/first", 100, 50, 50, 50),
            FilesystemInfo("/second", 200, 50, 150, 25),
        ],
    )

    async def run() -> None:
        app = DiskHawkApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.press("s")
            await pilot.press("/")
            await pilot.press("s", "e", "c")
            await pilot.pause()
            assert app.search_text == "sec"
            assert app.query_one("#filesystems").row_count == 1
            await pilot.press("escape")
            await pilot.press("r")
            await pilot.pause()
            assert "refreshed" in str(app.query_one("#status").content).lower()
            await pilot.press("e")
            await pilot.pause()
            assert (tmp_path / "diskhawk-report.json").exists()

    asyncio.run(run())


def test_tui_small_terminal_hint(monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.tui.app.relevant_filesystems", lambda: [])

    async def run() -> None:
        app = DiskHawkApp()
        async with app.run_test(size=(70, 20)) as pilot:
            await pilot.pause()
            assert "at least 80" in str(app.query_one("#status").content)

    asyncio.run(run())


def test_tui_background_scan_results_and_details(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diskhawk.tui.app.relevant_filesystems", lambda: [])
    monkeypatch.setattr(
        "diskhawk.tui.app.scan_directory",
        lambda path, **kwargs: _scan_summary(path),
    )

    async def run() -> None:
        app = DiskHawkApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#scan")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert app.view_mode == "scan"
            assert app.query_one("#filesystems").row_count == 1
            app.query_one("#filesystems").move_cursor(row=0)
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "MessageScreen"
            assert "item.txt" in str(app.screen.query_one("#modal-message").content)

    asyncio.run(run())


def test_ctrl_c_cancels_scan_without_exiting(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diskhawk.tui.app.relevant_filesystems", lambda: [])
    scan_started = threading.Event()

    def wait_for_cancel(path, *, cancelled, **kwargs):
        scan_started.set()
        while not cancelled():
            time.sleep(0.005)
        summary = _scan_summary(path)
        return ScanSummary(
            **{
                **summary.__dict__,
                "complete": False,
                "warnings": ("Scan cancelled; displayed sizes are partial.",),
            }
        )

    monkeypatch.setattr("diskhawk.tui.app.scan_directory", wait_for_cancel)

    async def run() -> None:
        app = DiskHawkApp()
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            await pilot.click("#scan")
            assert await asyncio.to_thread(scan_started.wait, 1)
            await pilot.press("ctrl+c")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert not app.scan_active
            assert app.screen is app.screen_stack[0]
            assert "Partial scan" in str(app.query_one("#status").content)

    asyncio.run(run())
