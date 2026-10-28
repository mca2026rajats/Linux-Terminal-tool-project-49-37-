from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Static

from diskhawk.config.manager import load_config
from diskhawk.core.disk_info import relevant_filesystems
from diskhawk.core.models import FilesystemInfo, ScanEntry, ScanSummary
from diskhawk.core.reports import build_report, render_json
from diskhawk.core.scanner import scan_directory
from diskhawk.core.size_format import format_bytes, usage_meter


class MessageScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("q", "dismiss_modal", "Close"),
    ]

    def __init__(self, title: str, message: str) -> None:
        super().__init__()
        self.title = title
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal"):
            yield Static(self.title, id="modal-title")
            yield Static(self.message, id="modal-message")
            yield Button("Close", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()

    def action_dismiss_modal(self) -> None:
        self.dismiss()


class DiskHawkApp(App[None]):
    TITLE = "DiskHawk"
    CSS_PATH = "theme.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "details", "Details"),
        Binding("escape", "clear_search", "Clear search"),
        Binding("slash", "search", "Search"),
        Binding("s", "sort", "Sort"),
        Binding("f", "search", "Filter"),
        Binding("e", "export", "Export"),
        Binding("c", "copy_path", "Copy path"),
        Binding("o", "reveal_path", "Reveal"),
        Binding("ctrl+c", "cancel_or_quit", "Cancel scan / quit"),
        Binding("j", "move_down", "Down"),
        Binding("k", "move_up", "Up"),
        Binding("g", "move_first", "First"),
        Binding("G", "move_last", "Last"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.filesystems: list[FilesystemInfo] = []
        self.scan_entries: list[ScanEntry] = []
        self.scan_summary: ScanSummary | None = None
        self.scan_root = Path.cwd()
        self.view_mode = "filesystems"
        self.sort_key = "mount"
        self.sort_reverse = False
        self.search_text = ""
        self.scan_active = False
        self.scan_cancelled = threading.Event()
        self.quit_after_scan = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Loading disk summary…", id="summary")
        yield Input(placeholder="Filter mount points", id="search", classes="hidden")
        yield DataTable(id="filesystems", cursor_type="row")
        yield Static("Ready", id="status", classes="status")
        yield Button("Scan current folder", id="scan")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#filesystems", DataTable).focus()
        try:
            self.filesystems = relevant_filesystems()
            self._refresh_table()
            docker_status = "available" if shutil.which("docker") else "not installed"
            self.query_one("#summary", Static).update(
                f"Disk capacity and available space · Docker CLI "
                f"{docker_status} · sizes use binary units"
            )
            self.query_one("#status", Static).update(
                "Ready · scans are read-only; directory sizes are estimates"
                if self.filesystems
                else "No supported filesystems found."
            )
        except (OSError, RuntimeError) as exc:
            self.query_one("#summary", Static).update(f"Disk summary unavailable: {exc}")

    def _refresh_table(self) -> None:
        table = self.query_one("#filesystems", DataTable)
        table.clear(columns=True)
        if self.view_mode == "scan":
            table.add_columns("Type", "Logical size", "Allocated est.", "Depth", "Path")
            entries = [
                entry
                for entry in self.scan_entries
                if self.search_text.casefold() in entry.relative_path.casefold()
            ]
            if self.sort_key == "size":
                entries.sort(key=lambda entry: entry.logical_bytes, reverse=self.sort_reverse)
            else:
                entries.sort(
                    key=lambda entry: entry.relative_path.casefold(),
                    reverse=self.sort_reverse,
                )
            for entry in entries:
                table.add_row(
                    entry.entry_type.upper(),
                    format_bytes(entry.logical_bytes),
                    format_bytes(entry.allocated_bytes),
                    str(entry.depth),
                    entry.relative_path,
                    key=entry.relative_path,
                )
        else:
            table.add_columns("Filesystem / mount", "Total", "Used", "Available", "Usage")
            filesystems = [
                item
                for item in self.filesystems
                if self.search_text.casefold() in item.mount_point.casefold()
            ]
            if self.sort_key == "size":
                filesystems.sort(key=lambda item: item.total_bytes, reverse=self.sort_reverse)
            else:
                filesystems.sort(
                    key=lambda item: item.mount_point.casefold(),
                    reverse=self.sort_reverse,
                )
            for item in filesystems:
                table.add_row(
                    item.mount_point,
                    format_bytes(item.total_bytes),
                    format_bytes(item.used_bytes),
                    format_bytes(item.available_bytes),
                    usage_meter(item.usage_percent),
                    key=item.mount_point,
                )

    def _selected_path(self) -> str | None:
        table = self.query_one("#filesystems", DataTable)
        row = table.cursor_row
        if self.view_mode == "scan":
            entries = [
                entry
                for entry in self.scan_entries
                if self.search_text.casefold() in entry.relative_path.casefold()
            ]
            entries.sort(
                key=(lambda entry: entry.logical_bytes)
                if self.sort_key == "size"
                else (lambda entry: entry.relative_path.casefold()),
                reverse=self.sort_reverse,
            )
            if not 0 <= row < len(entries):
                return None
            return str(self.scan_root / entries[row].relative_path)
        filesystems = [
            item
            for item in self.filesystems
            if self.search_text.casefold() in item.mount_point.casefold()
        ]
        filesystems.sort(
            key=(lambda item: item.total_bytes)
            if self.sort_key == "size"
            else (lambda item: item.mount_point.casefold()),
            reverse=self.sort_reverse,
        )
        return filesystems[row].mount_point if 0 <= row < len(filesystems) else None

    def action_refresh(self) -> None:
        if self.scan_active:
            self.query_one("#status", Static).update(
                "A scan is active; refresh is temporarily disabled."
            )
            return
        if self.view_mode == "scan":
            self._start_scan()
            return
        try:
            self.filesystems = relevant_filesystems()
            self._refresh_table()
            self.query_one("#status", Static).update("Disk summary refreshed.")
        except (OSError, RuntimeError) as exc:
            self.query_one("#status", Static).update(f"Refresh failed: {exc}")

    def action_quit(self) -> None:
        if self.scan_active:
            self.quit_after_scan = True
            self.scan_cancelled.set()
            self.query_one("#status", Static).update("Cancelling scan before exit…")
            return
        self.exit()

    def action_cancel_or_quit(self) -> None:
        if self.scan_active:
            self.scan_cancelled.set()
            self.query_one("#status", Static).update("Cancelling scan; results will be partial.")
            return
        self.exit()

    def action_move_down(self) -> None:
        self.query_one("#filesystems", DataTable).action_cursor_down()

    def action_move_up(self) -> None:
        self.query_one("#filesystems", DataTable).action_cursor_up()

    def action_move_first(self) -> None:
        self.query_one("#filesystems", DataTable).move_cursor(row=0)

    def action_move_last(self) -> None:
        table = self.query_one("#filesystems", DataTable)
        if table.row_count:
            table.move_cursor(row=table.row_count - 1)

    def action_details(self) -> None:
        selected = self._selected_path()
        if selected is None:
            return
        if self.view_mode == "scan":
            entry = next(
                (
                    row
                    for row in self.scan_entries
                    if str(self.scan_root / row.relative_path) == selected
                ),
                None,
            )
            if entry is not None:
                self.push_screen(
                    MessageScreen(
                        "Scan entry details",
                        f"Path: {entry.relative_path}\nType: {entry.entry_type}\n"
                        f"Logical size: {format_bytes(entry.logical_bytes)}\n"
                        f"Allocated estimate: {format_bytes(entry.allocated_bytes)}\n"
                        f"Depth: {entry.depth}",
                    )
                )
            return
        item = next(
            (row for row in self.filesystems if row.mount_point == selected),
            None,
        )
        if item is None:
            return
        message = (
            f"Mount: {item.mount_point}\nTotal: {format_bytes(item.total_bytes)}\n"
            f"Used: {format_bytes(item.used_bytes)}\n"
            f"Available: {format_bytes(item.available_bytes)}\n"
            f"Usage: {item.usage_percent:.1f}%"
        )
        self.push_screen(MessageScreen("Filesystem details", message))

    def action_help(self) -> None:
        self.push_screen(
            MessageScreen(
                "Keyboard help",
                "q quit · Ctrl+C cancel scan / quit · ? help · r refresh · Enter details · "
                "↑/↓ or j/k move · g/G first/last · / search · s sort · f filter · "
                "e export · c copy path · o reveal in Finder · Tab/Shift+Tab focus · "
                "Esc clear search",
            )
        )

    def action_search(self) -> None:
        field = self.query_one("#search", Input)
        field.remove_class("hidden")
        field.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.search_text = event.value
            self._refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_details()

    def action_clear_search(self) -> None:
        field = self.query_one("#search", Input)
        if field.has_focus or field.value:
            field.value = ""
            self.search_text = ""
            field.add_class("hidden")
            self.query_one("#filesystems", DataTable).focus()
        elif self.screen is not self.screen_stack[0]:
            self.pop_screen()
        self._refresh_table()

    def action_sort(self) -> None:
        if self.sort_key == "mount":
            self.sort_key = "size"
        else:
            self.sort_key = "mount"
            self.sort_reverse = not self.sort_reverse
        self._refresh_table()
        self.query_one("#status", Static).update(
            f"Sorted by {self.sort_key} ({'descending' if self.sort_reverse else 'ascending'})."
        )

    def action_export(self) -> None:
        try:
            data = build_report(
                self.filesystems,
                load_config(),
                scan=self.scan_summary,
            )
            target = Path.cwd() / "diskhawk-report.json"
            suffix = 1
            while target.exists():
                target = Path.cwd() / f"diskhawk-report-{suffix}.json"
                suffix += 1
            target.write_text(render_json(data) + "\n", encoding="utf-8")
            self.query_one("#status", Static).update(f"Sanitized report saved to {target}")
        except (OSError, ValueError, RuntimeError) as exc:
            self.query_one("#status", Static).update(f"Report export failed: {exc}")

    def action_copy_path(self) -> None:
        selected = self._selected_path()
        if selected is None:
            self.query_one("#status", Static).update("No filesystem selected.")
            return
        try:
            subprocess.run(["pbcopy"], input=selected, text=True, check=True, timeout=2)
        except (OSError, subprocess.SubprocessError) as exc:
            self.query_one("#status", Static).update(f"Copy unavailable: {exc}")
        else:
            self.query_one("#status", Static).update("Mount path copied.")

    def action_reveal_path(self) -> None:
        selected = self._selected_path()
        if selected is None:
            self.query_one("#status", Static).update("No filesystem selected.")
            return
        try:
            subprocess.run(["open", "-R", selected], check=True, timeout=5)
        except (OSError, subprocess.SubprocessError) as exc:
            self.query_one("#status", Static).update(f"Could not reveal path: {exc}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan" and not self.scan_active:
            self._start_scan()

    def _start_scan(self) -> None:
        self.scan_active = True
        self.view_mode = "scan"
        self.scan_root = Path.cwd()
        self.scan_summary = None
        self.scan_entries = []
        self._refresh_table()
        self.scan_cancelled.clear()
        self.quit_after_scan = False
        self.query_one("#status", Static).update("Scanning current folder… Ctrl+C cancels.")
        self._scan_worker()

    @work(thread=True, exclusive=True, name="diskhawk-scan")
    def _scan_worker(self) -> None:
        try:
            config = load_config()
            summary = scan_directory(
                self.scan_root,
                top=config.top,
                exclude=config.exclude_patterns,
                cancelled=self.scan_cancelled.is_set,
                progress=lambda files, directories, errors: self.call_from_thread(
                    self._set_scan_progress, files, directories, errors
                ),
            )
            self.call_from_thread(self._set_scan_result, summary)
        except (OSError, ValueError, RuntimeError) as exc:
            self.call_from_thread(self._set_status, f"Scan failed: {exc}")
        finally:
            self.call_from_thread(self._set_scan_active, False)

    def _set_scan_progress(self, files: int, directories: int, errors: int) -> None:
        self.query_one("#status", Static).update(
            f"Scanning… {files} files · {directories} directories · {errors} errors"
        )

    def _set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _set_scan_result(self, summary: ScanSummary) -> None:
        self.scan_summary = summary
        self.scan_entries = list(summary.top_entries)
        self._refresh_table()
        self.query_one("#filesystems", DataTable).focus()
        text = (
            f"{'Complete' if summary.complete else 'Partial'} scan: "
            f"{summary.files_visited} files · {summary.directories_visited} directories · "
            f"{summary.errors} errors · {format_bytes(summary.total_logical_bytes)} logical bytes. "
            "Directory sizes are estimates, not guaranteed reclaimable space."
        )
        if not self.scan_entries:
            text = f"{text} No matching entries."
        self.query_one("#status", Static).update(text)

    def _set_scan_active(self, active: bool) -> None:
        self.scan_active = active
        if not active and self.quit_after_scan:
            self.exit()

    def on_resize(self) -> None:
        if self.size.width < 80 or self.size.height < 24:
            self.query_one("#status", Static).update(
                "Terminal too small; resize to at least 80 × 24."
            )
