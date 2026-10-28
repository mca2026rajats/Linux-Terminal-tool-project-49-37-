from __future__ import annotations

from typing import Any

from diskhawk.core.models import DiskHawkConfig

_ALLOWED = {
    "schema_version",
    "warning_threshold_percent",
    "top",
    "exclude_patterns",
    "color",
    "docker_enabled",
    "report_format",
    "report_directory",
    "compact_tables",
}


def validate_config(data: Any) -> DiskHawkConfig:
    if not isinstance(data, dict):
        raise ValueError("Configuration must be a JSON object.")
    unknown = set(data) - _ALLOWED
    if unknown:
        raise ValueError(f"Unknown configuration key(s): {', '.join(sorted(unknown))}.")
    version = data.get("schema_version", 1)
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise ValueError(f"Unsupported configuration schema version: {version!r}.")
    threshold = data.get("warning_threshold_percent", 90)
    top = data.get("top", 20)
    excludes = data.get("exclude_patterns", [])
    color = data.get("color", "auto")
    docker = data.get("docker_enabled", True)
    report_format = data.get("report_format", "text")
    report_directory = data.get("report_directory")
    compact = data.get("compact_tables", False)
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 1 <= threshold <= 100:
        raise ValueError("warning_threshold_percent must be an integer from 1 to 100.")
    if not isinstance(top, int) or isinstance(top, bool) or not 1 <= top <= 500:
        raise ValueError("top must be an integer from 1 to 500.")
    if not isinstance(excludes, list) or not all(isinstance(item, str) for item in excludes):
        raise ValueError("exclude_patterns must be a list of strings.")
    if not isinstance(color, str) or color not in {"auto", "always", "never"}:
        raise ValueError("color must be auto, always, or never.")
    if not isinstance(docker, bool) or not isinstance(compact, bool):
        raise ValueError("docker_enabled and compact_tables must be booleans.")
    if not isinstance(report_format, str) or report_format not in {"json", "text"}:
        raise ValueError("report_format must be json or text.")
    if report_directory is not None and not isinstance(report_directory, str):
        raise ValueError("report_directory must be a string or null.")
    return DiskHawkConfig(
        schema_version=version,
        warning_threshold_percent=threshold,
        top=top,
        exclude_patterns=tuple(excludes),
        color=color,
        docker_enabled=docker,
        report_format=report_format,
        report_directory=report_directory,
        compact_tables=compact,
    )
