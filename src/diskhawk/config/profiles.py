from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from diskhawk.config.manager import atomic_write_json
from diskhawk.config.schema import validate_config
from diskhawk.core.models import DiskHawkConfig

_APP = "DiskHawk"


def export_profile(path: Path, config: DiskHawkConfig) -> Path:
    config_data = config.as_dict()
    report_directory = config_data["report_directory"]
    if isinstance(report_directory, str) and Path(report_directory).is_absolute():
        config_data["report_directory"] = None
    data = {"app": _APP, **config_data}
    atomic_write_json(path, data, backup=False)
    return path


def import_profile(path: Path) -> DiskHawkConfig:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read profile: {exc}") from exc
    if not isinstance(data, dict) or data.get("app") != _APP:
        raise ValueError("Profile must be a DiskHawk JSON object.")
    config_data = {key: value for key, value in data.items() if key != "app"}
    return validate_config(config_data)
