from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from diskhawk.cli import app
from diskhawk.core.disk_activity import DiskActivity
from diskhawk.core.models import DiskHawkConfig, FilesystemInfo
from diskhawk.core.scanner import scan_directory
from diskhawk.presentation.scan_dashboard import LiveScanView

runner = CliRunner()


def test_cli_help_and_version() -> None:
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["version"]).stdout.strip() == "DiskHawk 1.0.0"
    assert runner.invoke(app, ["--version"]).exit_code == 0
    for command in ["info", "scan", "docker", "ask", "report", "ui", "profile", "shell"]:
        assert runner.invoke(app, [command, "--help"]).exit_code == 0


def test_info_json_uses_core_service(monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.cli.list_filesystems",
        lambda: [
            FilesystemInfo("/", 100, 40, 60, 40, source="/dev/test"),
        ],
    )
    monkeypatch.setattr(
        "diskhawk.cli.relevant_filesystems",
        lambda mounts: mounts,
    )
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["filesystems"][0]["available_bytes"] == 60
    assert "docker_cli_available" in data


def test_info_default_uses_pixel_dashboard(monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.cli.sample_disk_activity",
        lambda rows: DiskActivity(
            1_250_000, 12_500, "Measured over 1.00 s; not benchmark performance."
        ),
    )
    monkeypatch.setattr("diskhawk.cli.list_filesystems", lambda: [])
    monkeypatch.setattr(
        "diskhawk.cli.relevant_filesystems",
        lambda mounts: [FilesystemInfo("/System/Volumes/Data", 100, 25, 70, 25, "/dev/disk7s1")],
    )
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "PIXEL STORAGE TERMINAL" in result.stdout
    assert "SPACE USED" in result.stdout
    assert "SPACE FREE" in result.stdout
    assert "TOTAL CAPACITY" in result.stdout
    assert "disk7s1" in result.stdout
    assert "HARDWARE HEALTH NOT ASSESSED" in result.stdout
    assert "LIVE DISK ACTIVITY" in result.stdout
    assert "1.25 MB/s" in result.stdout
    assert "12.50 KB/s" in result.stdout
    assert "\x1b[" not in result.stdout


def test_info_json_does_not_wait_for_live_activity(monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.cli.sample_disk_activity",
        lambda rows: (_ for _ in ()).throw(AssertionError("JSON output must not sample")),
    )
    monkeypatch.setattr("diskhawk.cli.list_filesystems", lambda: [])
    monkeypatch.setattr(
        "diskhawk.cli.relevant_filesystems",
        lambda mounts: [FilesystemInfo("/", 100, 25, 70, 25, "/dev/disk7s1")],
    )
    result = runner.invoke(app, ["info", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["filesystems"][0]["used_bytes"] == 25


def test_info_gracefully_rejects_invalid_dashboard_data(monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.cli.sample_disk_activity",
        lambda rows: DiskActivity(None, None, "N/A: mocked in CLI test"),
    )
    monkeypatch.setattr("diskhawk.cli.list_filesystems", lambda: [])
    monkeypatch.setattr(
        "diskhawk.cli.relevant_filesystems",
        lambda mounts: [FilesystemInfo("/", 0, 0, 0, 0)],
    )
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 1
    assert "Disk information unavailable" in result.output


def test_scan_json_and_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    (tmp_path / "large").write_bytes(b"x" * 200)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json", "--top", "1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["total_logical_bytes"] == 200
    assert data["entries"][0]["path"] == "large"
    assert runner.invoke(app, ["scan", str(tmp_path), "--top", "0"]).exit_code != 0


def test_scan_human_output_uses_one_real_scan_and_results_dashboard(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "large file.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    real_scan = scan_directory
    calls = []

    def scan_once(path, **kwargs):
        calls.append(kwargs.get("progress_event"))
        return real_scan(path, **kwargs)

    monkeypatch.setattr("diskhawk.cli.scan_directory", scan_once)
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert len(calls) == 1
    assert calls[0] is None
    assert "SCAN COMPLETE" in result.stdout
    assert "FILES INSPECTED" in result.stdout
    assert "LARGEST SPACE CONSUMERS" in result.stdout
    assert "large file.bin" in result.stdout
    assert "SCANNING" not in result.stdout
    assert "\x1b[" not in result.stdout


def test_scan_terminal_animation_receives_actual_progress_events(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "large.bin").write_bytes(b"x" * 10)
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    output = StringIO()
    monkeypatch.setattr(
        "diskhawk.cli.dashboard_console",
        lambda **kwargs: Console(
            file=output,
            width=80,
            force_terminal=True,
        ),
    )
    live_views = []
    live_sessions = []

    class FakeLive:
        def __init__(self, renderable, **kwargs) -> None:
            self.renderable = renderable
            self.started = False
            self.stopped = False
            live_views.append(renderable)
            live_sessions.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr("diskhawk.cli.Live", FakeLive)
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert len(live_views) == 1
    live_view = live_views[0]
    assert isinstance(live_view, LiveScanView)
    assert live_sessions[0].started
    assert live_sessions[0].stopped
    assert live_view.progress.files_visited == 1
    assert live_view.progress.current_path == tmp_path / "large.bin"
    assert "SCAN COMPLETE" in output.getvalue()


def test_scan_failed_input_renders_failure_state(tmp_path: Path, monkeypatch) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("data", encoding="utf-8")
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    result = runner.invoke(app, ["scan", str(file_path)])
    assert result.exit_code == 2
    assert "SCAN FAILED" in result.stdout
    assert "Scan error:" not in result.stdout
    assert "SCAN COMPLETE" not in result.stdout


def test_scan_failure_before_work_does_not_start_animation(tmp_path: Path, monkeypatch) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("data", encoding="utf-8")
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    output = StringIO()
    monkeypatch.setattr(
        "diskhawk.cli.dashboard_console",
        lambda **kwargs: Console(file=output, width=80, force_terminal=True),
    )
    live_sessions = []

    class FakeLive:
        def __init__(self, renderable, **kwargs) -> None:
            self.started = False
            live_sessions.append(self)

        def start(self):
            self.started = True

        def stop(self):
            pass

    monkeypatch.setattr("diskhawk.cli.Live", FakeLive)
    result = runner.invoke(app, ["scan", str(file_path)])
    assert result.exit_code == 2
    assert live_sessions and not live_sessions[0].started
    assert "SCAN FAILED" in output.getvalue()


def test_scan_interruption_is_not_reported_as_success(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "file").write_text("data", encoding="utf-8")
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    real_scan = scan_directory

    def interrupted_scan(path, **kwargs):
        return real_scan(path, cancelled=lambda: True)

    monkeypatch.setattr("diskhawk.cli.scan_directory", interrupted_scan)
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 3
    assert "SCAN INTERRUPTED" in result.stdout
    assert "SCAN COMPLETE\n" not in result.stdout


def test_keyboard_interrupt_stops_live_animation_and_reports_interrupted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    output = StringIO()
    monkeypatch.setattr(
        "diskhawk.cli.dashboard_console",
        lambda **kwargs: Console(file=output, width=80, force_terminal=True),
    )
    live_sessions = []

    class FakeLive:
        def __init__(self, renderable, **kwargs) -> None:
            self.started = False
            self.stopped = False
            live_sessions.append(self)

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

    monkeypatch.setattr("diskhawk.cli.Live", FakeLive)
    monkeypatch.setattr(
        "diskhawk.core.scanner.os.scandir",
        lambda path: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 3
    assert live_sessions[0].started
    assert live_sessions[0].stopped
    assert "SCAN INTERRUPTED" in output.getvalue()


def test_ask_routes_info_and_unknown(monkeypatch) -> None:
    calls: list[bool] = []
    monkeypatch.setattr("diskhawk.cli.info", lambda: calls.append(True))
    assert runner.invoke(app, ["ask", "give", "me", "disk", "info"]).exit_code == 0
    assert calls == [True]
    unknown = runner.invoke(app, ["ask", "not", "supported"])
    assert unknown.exit_code == 2
    assert "give me disk info" in unknown.stdout


def test_docker_config_gate_is_read_only(monkeypatch) -> None:
    monkeypatch.setattr(
        "diskhawk.cli._config",
        lambda: DiskHawkConfig(docker_enabled=False),
    )
    monkeypatch.setattr(
        "diskhawk.cli.get_docker_usage",
        lambda: (_ for _ in ()).throw(AssertionError("Docker must not be queried")),
    )
    result = runner.invoke(app, ["docker"])
    assert result.exit_code == 4
    assert "disabled" in result.stdout


def test_report_creates_sanitized_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr(
        "diskhawk.cli.relevant_filesystems",
        lambda: [FilesystemInfo("/", 100, 40, 60, 40)],
    )
    result = runner.invoke(app, ["report", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads((tmp_path / "diskhawk-report.json").read_text())
    assert data["schema_version"] == 1
    duplicate = runner.invoke(app, ["report", "--format", "json"])
    assert duplicate.exit_code == 2


def test_report_scan_and_noninteractive_details(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr("diskhawk.cli.relevant_filesystems", lambda: [])
    scan_path = tmp_path / "folder"
    scan_path.mkdir()
    (scan_path / "relative-name").write_text("content", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "report",
            "--format",
            "json",
            "--scan-path",
            str(scan_path),
            "--include-details",
            "--yes-include-details",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    assert result.exit_code == 0
    data = json.loads((tmp_path / "report.json").read_text())
    assert data["scan"]["files_visited"] == 1
    assert data["scan"]["entries"][0]["path"] == "relative-name"


def test_detailed_report_requires_scan_path_and_named_opt_in(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    no_scan = runner.invoke(
        app, ["report", "--include-details", "--output", str(tmp_path / "no.json")]
    )
    assert no_scan.exit_code == 2
    result = runner.invoke(
        app,
        [
            "report",
            "--include-details",
            "--scan-path",
            ".",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )
    assert result.exit_code == 2
    assert not (tmp_path / "report.json").exists()


def test_profile_import_previews_then_saves_validated_values(tmp_path: Path, monkeypatch) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps({"app": "DiskHawk", "schema_version": 1, "top": 35}),
        encoding="utf-8",
    )
    saved = []
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    monkeypatch.setattr("diskhawk.cli.save_config", lambda config: saved.append(config))
    result = runner.invoke(app, ["profile", "import", str(profile), "--yes"])
    assert result.exit_code == 0
    assert saved[0].top == 35
    assert "top: 20 -> 35" in result.stdout
