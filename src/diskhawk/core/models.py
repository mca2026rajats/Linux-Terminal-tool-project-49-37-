from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict


@dataclass(frozen=True)
class FilesystemInfo:
    mount_point: str
    total_bytes: int
    used_bytes: int
    available_bytes: int
    usage_percent: float
    source: str | None = None
    filesystem_type: str | None = None
    network: bool = False


@dataclass(frozen=True)
class ScanEntry:
    relative_path: str
    entry_type: Literal["file", "directory"]
    logical_bytes: int
    allocated_bytes: int | None
    depth: int


@dataclass(frozen=True)
class ScanSummary:
    root: Path
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    files_visited: int
    directories_visited: int
    errors: int
    complete: bool
    depth_limited: bool
    total_logical_bytes: int
    top_entries: tuple[ScanEntry, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DockerUsage:
    state: Literal["available", "not_installed", "unavailable", "timeout", "details_unavailable"]
    context: str | None
    categories: dict[str, dict[str, int | None]]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DiskHawkConfig:
    schema_version: int = 1
    warning_threshold_percent: int = 90
    top: int = 20
    exclude_patterns: tuple[str, ...] = ()
    color: Literal["auto", "always", "never"] = "auto"
    docker_enabled: bool = True
    report_format: Literal["json", "text"] = "text"
    report_directory: str | None = None
    compact_tables: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "warning_threshold_percent": self.warning_threshold_percent,
            "top": self.top,
            "exclude_patterns": list(self.exclude_patterns),
            "color": self.color,
            "docker_enabled": self.docker_enabled,
            "report_format": self.report_format,
            "report_directory": self.report_directory,
            "compact_tables": self.compact_tables,
        }


class DiskHawkReport(TypedDict):
    schema_version: int
    app: dict[str, str]
    created_at: str
    platform: dict[str, str]
    filesystems: list[dict[str, int | float | str]]
    scan: dict[str, object] | None
    docker: dict[str, object] | None
    warnings: list[str]
    warning_count: int
    error_count: int
    settings: dict[str, object]
