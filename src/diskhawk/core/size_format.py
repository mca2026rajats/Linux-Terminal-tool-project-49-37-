from __future__ import annotations

import re

_SIZE_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgtpe]?i?b)?\s*$", re.IGNORECASE)
_UNITS = {
    "b": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "pb": 1000**5,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
    "pib": 1024**5,
}


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    amount = float(abs(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    index = 0
    while amount >= 1024 and index < len(units) - 1:
        amount /= 1024
        index += 1
    if index == 0:
        return f"{sign}{int(amount)} B"
    return f"{sign}{amount:.1f} {units[index]}"


def parse_size(value: str) -> int:
    match = _SIZE_RE.fullmatch(value)
    if match is None:
        raise ValueError(f"Invalid size {value!r}; use a number with B, MB, GB, MiB, or GiB.")
    amount = float(match.group(1))
    unit = (match.group(2) or "b").lower()
    return int(amount * _UNITS[unit])


def usage_percent(used_bytes: int, total_bytes: int) -> float:
    if total_bytes <= 0:
        return 0.0
    return max(0.0, min(100.0, used_bytes / total_bytes * 100))


def usage_meter(percent: float, *, width: int = 10) -> str:
    if width < 1:
        raise ValueError("width must be positive")
    bounded = max(0.0, min(100.0, percent))
    filled = round(bounded / 100 * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {bounded:.1f}%"
