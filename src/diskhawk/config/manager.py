from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from platformdirs import user_config_path

from diskhawk.config.schema import validate_config
from diskhawk.core.models import DiskHawkConfig


def default_config_path() -> Path:
    return Path(user_config_path("diskhawk", appauthor=False)) / "config.json"


def load_config(path: Path | None = None) -> DiskHawkConfig:
    target = path or default_config_path()
    if not target.exists():
        return DiskHawkConfig()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read configuration at {target}: {exc}") from exc
    return validate_config(data)


def atomic_write_json(path: Path, data: object, *, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if backup and path.exists():
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup_path.exists():
            from datetime import UTC, datetime

            backup_path = path.with_suffix(path.suffix + f".{datetime.now(UTC):%Y%m%dT%H%M%SZ}.bak")
        shutil.copy2(path, backup_path)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_name, path)
    except OSError:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def save_config(config: DiskHawkConfig, path: Path | None = None) -> Path:
    target = path or default_config_path()
    atomic_write_json(target, config.as_dict(), backup=True)
    return target
