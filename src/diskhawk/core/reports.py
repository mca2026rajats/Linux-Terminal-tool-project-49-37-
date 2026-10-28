from __future__ import annotations

import json
import platform
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from diskhawk import __version__
from diskhawk.core.models import DiskHawkConfig, DiskHawkReport, FilesystemInfo, ScanSummary
from diskhawk.core.size_format import format_bytes
from diskhawk.utils.privacy import sanitize_path

REPORT_SCHEMA_VERSION = 1


def build_report(
    filesystems: list[FilesystemInfo],
    config: DiskHawkConfig,
    *,
    scan: ScanSummary | None = None,
    docker: dict[str, Any] | None = None,
    include_details: bool = False,
) -> DiskHawkReport:
    home = Path.home()
    settings = config.as_dict()
    exclude_patterns = settings.pop("exclude_patterns")
    report_directory = settings["report_directory"]
    settings["report_directory"] = (
        None
        if isinstance(report_directory, str) and Path(report_directory).is_absolute()
        else report_directory
    )
    settings["exclude_pattern_count"] = len(exclude_patterns)
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "app": {"name": "DiskHawk", "version": __version__},
        "created_at": datetime.now(UTC).isoformat(),
        "platform": {
            "system": "macOS" if platform.system() == "Darwin" else platform.system(),
            "release": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
        },
        "filesystems": [
            {
                "mount_point": sanitize_path(item.mount_point, home=home),
                "total_bytes": item.total_bytes,
                "used_bytes": item.used_bytes,
                "available_bytes": item.available_bytes,
                "usage_percent": round(item.usage_percent, 2),
            }
            for item in filesystems
        ],
        "scan": None,
        "docker": docker
        if docker is not None
        else {
            "state": "not_queried",
            "cli_available": shutil.which("docker") is not None,
        },
        "warnings": [],
        "warning_count": 0,
        "error_count": 0,
        "settings": settings,
    }
    if scan is not None:
        scan_data: dict[str, Any] = {
            "files_visited": scan.files_visited,
            "directories_visited": scan.directories_visited,
            "errors": scan.errors,
            "complete": scan.complete,
            "depth_limited": scan.depth_limited,
            "aggregate_logical_bytes": scan.total_logical_bytes,
        }
        if include_details:
            scan_data["entries"] = [
                {
                    "path": entry.relative_path,
                    "type": entry.entry_type,
                    "logical_bytes": entry.logical_bytes,
                    "allocated_bytes": entry.allocated_bytes,
                }
                for entry in scan.top_entries
            ]
        report["scan"] = scan_data
        report["warnings"].extend(scan.warnings)
        report["error_count"] = scan.errors
    if docker is not None:
        docker_warnings = docker.get("warnings", [])
        if isinstance(docker_warnings, (list, tuple)):
            report["warnings"].extend(str(item) for item in docker_warnings)
    report["warning_count"] = len(report["warnings"])
    return report


def render_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def render_text(report: dict[str, Any]) -> str:
    lines = [
        "DiskHawk diagnostic report",
        f"Created: {report['created_at']}",
        "Platform: "
        f"{report['platform']['system']} {report['platform']['release']} "
        f"({report['platform']['architecture']})",
        "Filesystems:",
    ]
    for item in report["filesystems"]:
        lines.append(
            f"  {item['mount_point']}: {format_bytes(item['available_bytes'])} available of "
            f"{format_bytes(item['total_bytes'])} ({item['usage_percent']:.1f}% used)"
        )
    docker = report.get("docker")
    if docker:
        if "cli_available" in docker:
            cli_status = "available" if docker["cli_available"] else "not installed"
            lines.append(f"Docker CLI: {cli_status}; usage not queried.")
        else:
            lines.append(f"Docker usage: {docker.get('state', 'unknown')}.")
            for category, values in docker.get("categories", {}).items():
                lines.append(
                    f"  {category}: {format_bytes(values.get('size_bytes'))} total; "
                    f"{format_bytes(values.get('reclaimable_bytes'))} reclaimable estimate"
                )
    if report.get("scan"):
        scan = report["scan"]
        lines.append(
            f"Scan: {scan['files_visited']} files, {scan['directories_visited']} directories, "
            f"{scan['errors']} errors; {'complete' if scan['complete'] else 'partial'}"
        )
    lines.append(f"Warnings: {report['warning_count']} · Errors: {report['error_count']}")
    for warning in report["warnings"]:
        lines.append(f"Warning: {warning}")
    lines.append(
        "Privacy: home paths are shortened; file names are excluded unless explicitly requested."
    )
    return "\n".join(lines) + "\n"
