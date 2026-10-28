from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from diskhawk.cli import app
from diskhawk.core.models import DiskHawkConfig, FilesystemInfo

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


def test_scan_json_and_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("diskhawk.cli._config", lambda: DiskHawkConfig())
    (tmp_path / "large").write_bytes(b"x" * 200)
    result = runner.invoke(app, ["scan", str(tmp_path), "--json", "--top", "1"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["total_logical_bytes"] == 200
    assert data["entries"][0]["path"] == "large"
    assert runner.invoke(app, ["scan", str(tmp_path), "--top", "0"]).exit_code != 0


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
