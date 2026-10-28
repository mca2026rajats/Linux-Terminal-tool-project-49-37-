from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable

from diskhawk.core.models import DockerUsage
from diskhawk.utils.subprocesses import CommandResult, run_command

_VALUE = re.compile(r"^\s*([\d.]+)\s*([A-Za-z]+)?")


def _parse_docker_size(value: str) -> int | None:
    match = _VALUE.match(value)
    if match is None:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "B").lower()
    factors = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    return int(amount * factors[unit]) if unit in factors else None


def parse_docker_output(output: str) -> dict[str, dict[str, int | None]]:
    categories: dict[str, dict[str, int | None]] = {}
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        category = str(item.get("Type", item.get("type", ""))).strip()
        if not category:
            continue
        size = item.get("Size", item.get("size", ""))
        reclaimable = item.get("Reclaimable", item.get("reclaimable", ""))
        categories[category] = {
            "size_bytes": _parse_docker_size(str(size)),
            "reclaimable_bytes": _parse_docker_size(str(reclaimable)),
        }
    return categories


def get_docker_usage(
    *,
    executable: str | None = None,
    runner: Callable[..., CommandResult] = run_command,
    timeout: float = 10,
) -> DockerUsage:
    docker = executable if executable is not None else shutil.which("docker")
    if not docker:
        return DockerUsage("not_installed", None, {}, ("Docker CLI is not installed.",))
    try:
        context_result = runner([docker, "context", "show"], timeout=min(timeout, 5))
        context = context_result.stdout.strip() if context_result.returncode == 0 else None
        result = runner([docker, "system", "df", "--format", "{{json .}}"], timeout=timeout)
    except TimeoutError:
        return DockerUsage("timeout", None, {}, ("Docker command timed out.",))
    except RuntimeError as exc:
        return DockerUsage("unavailable", None, {}, (str(exc),))
    if result.returncode != 0:
        return DockerUsage(
            "unavailable",
            context,
            {},
            ("Docker daemon is unavailable or the usage command failed.",),
        )
    categories = parse_docker_output(result.stdout)
    if not categories:
        return DockerUsage(
            "details_unavailable", context, {}, ("Docker output could not be parsed.",)
        )
    warnings = ()
    if context and context != "default":
        warnings = (f"Docker context {context!r} may refer to a remote host.",)
    else:
        warnings = ("Docker usage is reported by the active Docker context.",)
    return DockerUsage("available", context, categories, warnings)
