from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from diskhawk.config.manager import atomic_write_json, load_config, save_config
from diskhawk.config.profiles import export_profile, import_profile
from diskhawk.config.schema import validate_config
from diskhawk.core.models import DiskHawkConfig, FilesystemInfo
from diskhawk.core.reports import build_report, render_json, render_text
from diskhawk.core.scanner import scan_directory
from diskhawk.utils.privacy import sanitize_path, sanitize_value


def test_config_defaults_and_validation() -> None:
    defaults = validate_config({})
    assert defaults == DiskHawkConfig()
    assert validate_config({"top": 30, "exclude_patterns": ["*.tmp"]}).top == 30
    invalid_values = [
        {"schema_version": 2},
        {"warning_threshold_percent": 0},
        {"top": 501},
        {"exclude_patterns": "bad"},
        {"color": "rainbow"},
        {"docker_enabled": "yes"},
        {"report_format": "xml"},
        {"report_directory": 4},
        {"unexpected": True},
        [],
    ]
    for data in invalid_values:
        with pytest.raises(ValueError):
            validate_config(data)


def test_config_load_save_and_backup(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    assert load_config(config_path) == DiskHawkConfig()
    save_config(DiskHawkConfig(top=10), config_path)
    assert load_config(config_path).top == 10
    save_config(DiskHawkConfig(top=11), config_path)
    assert load_config(config_path).top == 11
    backups = list(tmp_path.glob("config.json*.bak"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text())["top"] == 10
    config_path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="Could not read"):
        load_config(config_path)


def test_atomic_write_cleans_temporary_file_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "settings.json"
    real_replace = __import__("os").replace

    def fail_replace(source: str, dest: Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("diskhawk.config.manager.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_json(target, {"ok": True}, backup=False)
    assert not list(tmp_path.glob(".settings.json.*"))
    monkeypatch.setattr("diskhawk.config.manager.os.replace", real_replace)


def test_profile_roundtrip_and_rejection(tmp_path: Path) -> None:
    profile = tmp_path / "profile.json"
    config = DiskHawkConfig(top=14, color="never")
    export_profile(profile, config)
    assert import_profile(profile) == config
    profile.write_text(json.dumps({"app": "Other", "top": 5}), encoding="utf-8")
    with pytest.raises(ValueError, match="DiskHawk"):
        import_profile(profile)
    profile.write_text(json.dumps({"app": "DiskHawk", "schema_version": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        import_profile(profile)


def test_profile_export_omits_absolute_user_path(tmp_path: Path) -> None:
    profile = tmp_path / "portable.json"
    export_profile(profile, DiskHawkConfig(report_directory=str(tmp_path / "reports")))
    exported = json.loads(profile.read_text(encoding="utf-8"))
    assert exported["report_directory"] is None


def test_privacy_sanitizes_home_prefix_and_nested_values(tmp_path: Path) -> None:
    home = tmp_path / "users" / "test"
    private = home / "folder" / "name"
    assert sanitize_path(home, home=home) == "~"
    assert sanitize_path(private, home=home) == "~/folder/name"
    assert sanitize_path("/private/path", home=home) == "/private/path"
    sanitized = sanitize_value(
        {"path": private, "items": [str(private)], "safe": "redacted"},
        home=home,
    )
    assert sanitized == {
        "path": "~/folder/name",
        "items": ["~/folder/name"],
        "safe": "redacted",
    }


def test_report_schema_omits_private_paths_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    file = scan_root / "private-name.txt"
    file.write_text("secret file content", encoding="utf-8")
    summary = scan_directory(scan_root)
    config = DiskHawkConfig(report_directory=str(home / "Reports"))
    filesystem = FilesystemInfo(
        str(home),
        100,
        40,
        60,
        40,
        source="/dev/disk-test",
    )
    report = build_report([filesystem], config, scan=summary)
    encoded = render_json(report)
    assert report["schema_version"] == 1
    assert report["docker"]["state"] == "not_queried"
    assert report["error_count"] == 0
    assert report["warning_count"] == 0
    assert report["filesystems"][0]["mount_point"] == "~"
    assert report["settings"]["report_directory"] is None
    assert "private-name.txt" not in encoded
    assert "secret file content" not in encoded
    assert str(home) not in encoded
    assert report["scan"]["aggregate_logical_bytes"] == len("secret file content")
    assert "Privacy:" in render_text(report)
    detailed = build_report([filesystem], config, scan=summary, include_details=True)
    assert "private-name.txt" in render_json(detailed)


def test_report_json_is_valid() -> None:
    data = build_report([], DiskHawkConfig())
    assert json.loads(render_json(data))["app"]["name"] == "DiskHawk"


def test_report_includes_explicit_docker_and_partial_scan_warnings(tmp_path: Path) -> None:
    (tmp_path / "item").write_text("abc", encoding="utf-8")
    scan = replace(
        scan_directory(tmp_path),
        complete=False,
        errors=2,
        warnings=("Scan was partial.",),
    )
    report = build_report(
        [],
        DiskHawkConfig(),
        scan=scan,
        docker={
            "state": "available",
            "context": "remote",
            "categories": {"Images": {"size_bytes": 2048, "reclaimable_bytes": 1024}},
            "warnings": ["Docker context may be remote."],
        },
    )
    assert report["error_count"] == 2
    assert report["warning_count"] == 2
    assert "entries" not in report["scan"]
    text = render_text(report)
    assert "Docker usage: available" in text
    assert "Images: 2.0 KiB total; 1.0 KiB reclaimable estimate" in text
    assert "partial" in text
    assert "Warning: Docker context may be remote." in text
