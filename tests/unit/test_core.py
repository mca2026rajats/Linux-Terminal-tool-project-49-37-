from __future__ import annotations

import os
from pathlib import Path

import pytest

from diskhawk.core import disk_info, docker_info
from diskhawk.core.models import FilesystemInfo
from diskhawk.core.phrase_router import Action, normalize_phrase, route_phrase, supported_phrases
from diskhawk.core.scanner import scan_directory
from diskhawk.core.size_format import format_bytes, parse_size, usage_meter, usage_percent
from diskhawk.utils.subprocesses import CommandResult, run_command


def test_size_format_and_parse() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(1536) == "1.5 KiB"
    assert format_bytes(None) == "N/A"
    assert format_bytes(-1024) == "-1.0 KiB"
    assert parse_size("100MB") == 100_000_000
    assert parse_size("1.5 GiB") == int(1.5 * 1024**3)
    with pytest.raises(ValueError):
        parse_size("nope")
    assert usage_percent(10, 0) == 0
    assert usage_percent(50, 100) == 50
    assert usage_percent(120, 100) == 100
    assert usage_meter(50) == "[█████░░░░░] 50.0%"
    with pytest.raises(ValueError):
        usage_meter(50, width=0)


def test_parse_df_output_with_mount_spaces() -> None:
    output = (
        "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
        "/dev/disk3 1000 300 700 30% /Volumes/External Disk\n"
        "network:/share 2000 1000 1000 50% /Volumes/Team Drive\n"
        "bad row\n"
        "/dev/bad not-a-number 1 2 3% /broken\n"
    )
    rows = disk_info._df_rows(output)
    assert len(rows) == 2
    assert rows[0].mount_point == "/Volumes/External Disk"
    assert rows[0].total_bytes == 1_024_000
    assert rows[1].network is True
    assert rows[1].mount_point == "/Volumes/Team Drive"


def test_list_filesystems_handles_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        disk_info.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "head\n/dev/a 1 0 1 0% /\n"}
        )(),
    )
    assert len(disk_info.list_filesystems()) == 1
    monkeypatch.setattr(
        disk_info.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 1, "stdout": "", "stderr": "bad df"}
        )(),
    )
    with pytest.raises(RuntimeError, match="bad df"):
        disk_info.list_filesystems()


def test_relevant_and_supported_mounts() -> None:
    mounts = [
        FilesystemInfo("/", 100, 50, 50, 50, source="/dev/disk1"),
        FilesystemInfo("/System/Volumes/Data", 100, 50, 50, 50, source="/dev/disk1"),
        FilesystemInfo("/Volumes/Work", 100, 50, 50, 50, source="/dev/disk2"),
        FilesystemInfo("/Volumes/NAS", 100, 50, 50, 50, source="nas:/share", network=True),
        FilesystemInfo("/dev", 100, 50, 50, 50, source="devfs"),
    ]
    relevant = disk_info.relevant_filesystems(
        mounts,
        root_path=Path("/"),
        home_path=Path("/Users/test"),
        current_path=Path("/Volumes/Work/repo"),
    )
    assert [row.source for row in relevant] == ["/dev/disk1", "/dev/disk2"]
    assert [row.mount_point for row in disk_info.supported_filesystems(mounts)] == [
        "/",
        "/System/Volumes/Data",
        "/Volumes/Work",
    ]
    assert len(disk_info.supported_filesystems(mounts, include_network=True)) == 4
    assert disk_info.platform_label().startswith("macOS ")


def test_relevant_filesystem_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(disk_info, "_disk_usage", lambda path: (10, 4, 6))
    result = disk_info.relevant_filesystems(
        [],
        root_path=tmp_path,
        home_path=tmp_path,
        current_path=tmp_path,
    )
    assert len(result) == 1
    assert result[0].total_bytes == 10


def test_scanner_reports_nested_items_and_skips_symlinks(tmp_path: Path) -> None:
    (tmp_path / ".hidden").write_bytes(b"abc")
    sub = tmp_path / "nested"
    sub.mkdir()
    (sub / "large.bin").write_bytes(b"x" * 2048)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.write_bytes(b"secret")
    try:
        (tmp_path / "linked").symlink_to(outside)
    except OSError:
        pass
    result = scan_directory(tmp_path, top=10)
    files = [entry for entry in result.top_entries if entry.entry_type == "file"]
    directories = [entry for entry in result.top_entries if entry.entry_type == "directory"]
    assert result.complete
    assert result.files_visited == 2
    assert result.total_logical_bytes == 2051
    assert any(
        entry.relative_path == "nested" and entry.logical_bytes == 2048 for entry in directories
    )
    assert any(entry.relative_path == ".hidden" for entry in files)
    assert all(entry.relative_path != "linked" for entry in result.top_entries)
    outside.unlink(missing_ok=True)


def test_scanner_exclusions_min_size_and_depth(tmp_path: Path) -> None:
    (tmp_path / "keep.txt").write_bytes(b"12345")
    excluded = tmp_path / "skip"
    excluded.mkdir()
    (excluded / "file.bin").write_bytes(b"123456789")
    deep = tmp_path / "deep"
    deep.mkdir()
    (deep / "inside").write_bytes(b"1234567")
    result = scan_directory(tmp_path, exclude=["skip"], min_size=4, max_depth=1)
    assert not result.complete
    assert result.depth_limited
    assert result.files_visited == 1
    assert all(entry.logical_bytes >= 4 for entry in result.top_entries)
    assert not any("skip" in entry.relative_path for entry in result.top_entries)


def test_scanner_hardlinks_and_progress(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"abc" * 100)
    try:
        os.link(source, tmp_path / "linked")
    except OSError:
        pytest.skip("Hard links are not available")
    progress: list[tuple[int, int, int]] = []
    result = scan_directory(tmp_path, progress=lambda *values: progress.append(values))
    allocations = [
        entry.allocated_bytes for entry in result.top_entries if entry.entry_type == "file"
    ]
    assert result.total_logical_bytes == 600
    assert sum(value or 0 for value in allocations) == source.stat().st_blocks * 512
    assert progress == []


def test_scanner_exposes_actual_progress_events(tmp_path: Path) -> None:
    (tmp_path / "first").write_bytes(b"abc")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "second").write_bytes(b"12345")
    events = []

    result = scan_directory(tmp_path, progress_event=events.append)

    assert result.files_visited == 2
    assert result.directories_visited == 2
    assert events
    assert events[0].current_path == tmp_path
    assert events[0].files_visited == 0
    assert events[-1].files_visited == 2
    assert events[-1].directories_visited == 2
    assert events[-1].current_path == nested / "second"
    assert all(event.elapsed_seconds >= 0 for event in events)


def test_scanner_cancellation_and_validation(tmp_path: Path) -> None:
    (tmp_path / "file").write_text("x")
    result = scan_directory(tmp_path, cancelled=lambda: True)
    assert not result.complete
    assert "cancelled" in result.warnings[0].lower()
    with pytest.raises(ValueError, match="positive"):
        scan_directory(tmp_path, top=0)
    with pytest.raises(ValueError, match="not be negative"):
        scan_directory(tmp_path, min_size=-1)
    with pytest.raises(ValueError, match="not a directory"):
        scan_directory(tmp_path / "file")
    with pytest.raises(ValueError, match="requires --allow-root"):
        scan_directory("/")


def test_scanner_turns_keyboard_interrupt_into_partial_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "diskhawk.core.scanner.os.scandir",
        lambda path: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    result = scan_directory(tmp_path)
    assert not result.complete
    assert result.files_visited == 0
    assert result.directories_visited == 1
    assert any("interrupted" in warning.casefold() for warning in result.warnings)


def test_scanner_counts_filesystem_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    child = tmp_path / "locked"
    child.mkdir()
    real_scandir = os.scandir

    def failing_scandir(path: os.PathLike[str] | str):
        if Path(path) == child:
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr("diskhawk.core.scanner.os.scandir", failing_scandir)
    result = scan_directory(tmp_path)
    assert not result.complete
    assert result.errors == 1


def test_scanner_marks_an_unreadable_root_as_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "diskhawk.core.scanner.os.scandir",
        lambda path: (_ for _ in ()).throw(PermissionError("denied")),
    )
    result = scan_directory(tmp_path)
    assert not result.complete
    assert result.root_error
    assert result.errors == 1


def test_phrase_router_is_deterministic() -> None:
    assert normalize_phrase("  GIVE   me Disk Info ") == "give me disk info"
    assert route_phrase("GIVE me disk info") == Action.INFO
    assert route_phrase("scan current folder") == Action.SCAN
    assert route_phrase("docker disk usage") == Action.DOCKER
    assert len(supported_phrases()) == 8
    with pytest.raises(ValueError, match="Unrecognized"):
        route_phrase("run a command")


def test_docker_output_parser_and_states(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = "\n".join(
        [
            '{"Type":"Images","Size":"1.5GB","Reclaimable":"500MB (33%)"}',
            '{"Type":"Containers","Size":"10MiB","Reclaimable":"0B (0%)"}',
            "not json",
        ]
    )
    parsed = docker_info.parse_docker_output(lines)
    assert parsed["Images"]["size_bytes"] == 1_500_000_000
    assert parsed["Images"]["reclaimable_bytes"] == 500_000_000
    assert parsed["Containers"]["size_bytes"] == 10 * 1024**2
    assert docker_info.parse_docker_output("garbage") == {}
    assert docker_info._parse_docker_size("oops") is None

    class Runner:
        def __init__(
            self, results: list[CommandResult] | None = None, error: Exception | None = None
        ):
            self.results = results or []
            self.error = error

        def __call__(self, *args, **kwargs):
            if self.error:
                raise self.error
            return self.results.pop(0)

    assert docker_info.get_docker_usage(executable="", runner=Runner()).state == "not_installed"
    available = docker_info.get_docker_usage(
        executable="docker",
        runner=Runner(
            [
                CommandResult(0, "remote-context\n", ""),
                CommandResult(0, '{"Type":"Images","Size":"1GB","Reclaimable":"1GB"}\n', ""),
            ]
        ),
    )
    assert available.state == "available"
    assert "remote" in available.warnings[0]
    assert (
        docker_info.get_docker_usage(executable="docker", runner=Runner(error=TimeoutError())).state
        == "timeout"
    )
    assert (
        docker_info.get_docker_usage(
            executable="docker", runner=Runner(error=RuntimeError("missing"))
        ).state
        == "unavailable"
    )
    assert (
        docker_info.get_docker_usage(
            executable="docker",
            runner=Runner([CommandResult(0, "default\n", ""), CommandResult(1, "", "error")]),
        ).state
        == "unavailable"
    )
    assert (
        docker_info.get_docker_usage(
            executable="docker",
            runner=Runner([CommandResult(1, "", ""), CommandResult(0, "n/a", "")]),
        ).state
        == "details_unavailable"
    )


def test_run_command_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "diskhawk.utils.subprocesses.subprocess.run",
        lambda *args, **kwargs: type(
            "Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""}
        )(),
    )
    assert run_command(["echo", "ok"], timeout=1).stdout == "ok"
    monkeypatch.setattr(
        "diskhawk.utils.subprocesses.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            __import__("subprocess").TimeoutExpired("cmd", 1)
        ),
    )
    with pytest.raises(TimeoutError):
        run_command(["wait"], timeout=1)
    with pytest.raises(ValueError):
        run_command([], timeout=1)
