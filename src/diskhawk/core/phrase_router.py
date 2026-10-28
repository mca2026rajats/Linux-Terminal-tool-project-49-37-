from __future__ import annotations

import re
from enum import StrEnum


class Action(StrEnum):
    INFO = "info"
    SCAN = "scan"
    DOCKER = "docker"


_PHRASES = {
    "give me disk info": Action.INFO,
    "show disk info": Action.INFO,
    "disk info": Action.INFO,
    "check disk space": Action.INFO,
    "how much disk space is left": Action.INFO,
    "scan current folder": Action.SCAN,
    "find large files": Action.SCAN,
    "docker disk usage": Action.DOCKER,
}


def normalize_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def route_phrase(text: str) -> Action:
    try:
        return _PHRASES[normalize_phrase(text)]
    except KeyError as exc:
        raise ValueError(f"Unrecognized request: {text}") from exc


def supported_phrases() -> tuple[str, ...]:
    return tuple(_PHRASES)
