from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def sanitize_path(value: str | Path, *, home: Path | None = None) -> str:
    raw = str(value)
    home_path = (home or Path.home()).expanduser().resolve(strict=False)
    try:
        resolved = Path(raw).expanduser().resolve(strict=False)
        relative = resolved.relative_to(home_path)
    except (OSError, ValueError):
        return raw
    if str(relative) == ".":
        return "~"
    return f"~/{relative.as_posix()}"


def sanitize_value(value: Any, *, home: Path | None = None) -> Any:
    if isinstance(value, Path):
        return sanitize_path(value, home=home)
    if isinstance(value, dict):
        return {str(key): sanitize_value(item, home=home) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_value(item, home=home) for item in value]
    if isinstance(value, str) and value.startswith(os.path.sep):
        return sanitize_path(value, home=home)
    return value
