from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from diskhawk.core.models import FilesystemInfo
from diskhawk.core.size_format import usage_percent

_NETWORK_SOURCE = re.compile(r"^(//|[^/]+:)")
_PSEUDO_MOUNTS = ("/dev", "/net", "/proc", "/sys", "/private/var/run")


def _df_rows(output: str) -> list[FilesystemInfo]:
    rows: list[FilesystemInfo] = []
    lines = output.splitlines()
    for line in lines[1:]:
        columns = line.split(maxsplit=5)
        if len(columns) != 6:
            continue
        source, total_kib, used_kib, available_kib, _capacity, mount = columns
        try:
            total = int(total_kib) * 1024
            used = int(used_kib) * 1024
            available = int(available_kib) * 1024
        except ValueError:
            continue
        rows.append(
            FilesystemInfo(
                source=source,
                mount_point=mount,
                total_bytes=total,
                used_bytes=used,
                available_bytes=available,
                usage_percent=usage_percent(used, total),
                network=bool(_NETWORK_SOURCE.match(source)),
            )
        )
    return rows


def list_filesystems() -> list[FilesystemInfo]:
    try:
        completed = subprocess.run(
            ["df", "-Pk"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Could not enumerate mounted filesystems: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "df returned a non-zero status"
        raise RuntimeError(f"Could not enumerate mounted filesystems: {detail}")
    return _df_rows(completed.stdout)


def _disk_usage(path: Path) -> tuple[int, int, int]:
    usage = shutil.disk_usage(path)
    return usage.total, usage.used, usage.free


def _mount_for(path: Path, mounts: list[FilesystemInfo]) -> FilesystemInfo:
    resolved = path.resolve(strict=False)
    candidates = []
    for item in mounts:
        try:
            mount = Path(item.mount_point).resolve(strict=False)
            resolved.relative_to(mount)
        except (OSError, ValueError):
            continue
        candidates.append((len(str(mount)), item))
    if candidates:
        return max(candidates, key=lambda row: row[0])[1]
    total, used, available = _disk_usage(resolved)
    return FilesystemInfo(
        mount_point=str(resolved),
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        usage_percent=usage_percent(used, total),
    )


def relevant_filesystems(
    mounts: list[FilesystemInfo] | None = None,
    *,
    root_path: Path = Path("/"),
    home_path: Path | None = None,
    current_path: Path | None = None,
) -> list[FilesystemInfo]:
    available_mounts = mounts if mounts is not None else list_filesystems()
    home = home_path if home_path is not None else Path.home()
    current = current_path if current_path is not None else Path.cwd()
    selected = [
        _mount_for(root_path, available_mounts),
        _mount_for(home, available_mounts),
        _mount_for(current, available_mounts),
    ]
    unique: dict[str, FilesystemInfo] = {}
    for item in selected:
        unique.setdefault(item.source or item.mount_point, item)
    return list(unique.values())


def supported_filesystems(
    mounts: list[FilesystemInfo] | None = None,
    *,
    include_network: bool = False,
) -> list[FilesystemInfo]:
    available_mounts = mounts if mounts is not None else list_filesystems()
    result: dict[str, FilesystemInfo] = {}
    for item in available_mounts:
        mount = item.mount_point.rstrip("/") or "/"
        if any(mount == pseudo or mount.startswith(pseudo + "/") for pseudo in _PSEUDO_MOUNTS):
            continue
        if item.network and not include_network:
            continue
        if item.total_bytes <= 0:
            continue
        result.setdefault(item.mount_point, item)
    return list(result.values())


def platform_label() -> str:
    system = "macOS" if platform.system() == "Darwin" else platform.system()
    return f"{system} {platform.release()} ({platform.machine()})"
