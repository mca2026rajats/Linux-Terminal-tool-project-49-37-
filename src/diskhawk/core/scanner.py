from __future__ import annotations

import fnmatch
import heapq
import os
import stat
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from diskhawk.core.models import ScanEntry, ScanSummary

ProgressCallback = Callable[[int, int, int], None]


class ScanCancelled(Exception):
    """Raised when a caller requests cooperative scan cancellation."""


def _excluded(relative_path: str, patterns: Iterable[str]) -> bool:
    basename = Path(relative_path).name
    return any(
        fnmatch.fnmatchcase(relative_path, pattern) or fnmatch.fnmatchcase(basename, pattern)
        for pattern in patterns
    )


def scan_directory(
    path: Path | str = ".",
    *,
    top: int = 20,
    min_size: int = 0,
    max_depth: int | None = None,
    exclude: Iterable[str] = (),
    allow_root: bool = False,
    cancelled: Callable[[], bool] | None = None,
    progress: ProgressCallback | None = None,
) -> ScanSummary:
    if top < 1:
        raise ValueError("top must be a positive integer")
    if min_size < 0:
        raise ValueError("min_size must not be negative")
    if max_depth is not None and max_depth < 0:
        raise ValueError("max_depth must not be negative")

    root = Path(path).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Scan path is not a directory: {path}")
    if root == Path("/") and not allow_root:
        raise ValueError("Scanning / requires --allow-root.")

    started = datetime.now(UTC)
    clock = time.monotonic()
    patterns = tuple(exclude)
    errors = 0
    files = 0
    directories = 1
    total_logical_bytes = 0
    complete = True
    depth_limited = False
    warnings: list[str] = []
    dir_sizes: dict[str, list[int | None]] = {".": [0, 0]}
    dir_depth: dict[str, int] = {".": 0}
    top_heap: list[tuple[int, int, ScanEntry]] = []
    serial = 0
    seen_inodes: set[tuple[int, int]] = set()
    stack: list[tuple[Path, str, int]] = [(root, ".", 0)]

    def add_top(entry: ScanEntry) -> None:
        nonlocal serial
        if entry.logical_bytes < min_size:
            return
        serial += 1
        item = (entry.logical_bytes, serial, entry)
        if len(top_heap) < top:
            heapq.heappush(top_heap, item)
        elif item[0] > top_heap[0][0]:
            heapq.heapreplace(top_heap, item)

    try:
        while stack:
            if cancelled is not None and cancelled():
                complete = False
                warnings.append("Scan cancelled; displayed sizes are partial.")
                break
            directory, relative_dir, depth = stack.pop()
            try:
                children = list(os.scandir(directory))
            except OSError:
                errors += 1
                complete = False
                continue
            children.sort(key=lambda entry: entry.name.casefold())
            pending_dirs: list[tuple[Path, str, int]] = []
            for child in children:
                if cancelled is not None and cancelled():
                    complete = False
                    warnings.append("Scan cancelled; displayed sizes are partial.")
                    stack.clear()
                    break
                relative = (
                    str(Path(relative_dir) / child.name) if relative_dir != "." else child.name
                )
                if _excluded(relative, patterns):
                    continue
                try:
                    info = child.stat(follow_symlinks=False)
                except OSError:
                    errors += 1
                    complete = False
                    continue
                if stat.S_ISDIR(info.st_mode):
                    directories += 1
                    dir_sizes[relative] = [0, 0]
                    dir_depth[relative] = depth + 1
                    if max_depth is not None and depth + 1 >= max_depth:
                        try:
                            with os.scandir(child.path) as iterator:
                                has_children = next(iterator, None) is not None
                        except OSError:
                            errors += 1
                            complete = False
                            continue
                        if has_children:
                            depth_limited = True
                            complete = False
                        continue
                    pending_dirs.append((Path(child.path), relative, depth + 1))
                elif stat.S_ISREG(info.st_mode):
                    files += 1
                    logical = info.st_size
                    total_logical_bytes += logical
                    inode = (info.st_dev, info.st_ino)
                    allocated: int | None = getattr(info, "st_blocks", None)
                    allocated_bytes = allocated * 512 if allocated is not None else None
                    if allocated_bytes is not None and inode in seen_inodes:
                        allocated_bytes = 0
                    else:
                        seen_inodes.add(inode)
                    parent = relative_dir
                    while True:
                        totals = dir_sizes[parent]
                        totals[0] = int(totals[0]) + logical
                        if totals[1] is not None and allocated_bytes is not None:
                            totals[1] = int(totals[1]) + allocated_bytes
                        else:
                            totals[1] = None
                        if parent == ".":
                            break
                        parent = str(Path(parent).parent)
                    add_top(ScanEntry(relative, "file", logical, allocated_bytes, depth + 1))
                if progress is not None and (files + directories) % 100 == 0:
                    progress(files, directories, errors)
            stack.extend(reversed(pending_dirs))
    except KeyboardInterrupt:
        complete = False
        warnings.append("Scan interrupted; displayed sizes are partial.")

    for relative, totals in dir_sizes.items():
        if relative == ".":
            continue
        entry = ScanEntry(relative, "directory", int(totals[0]), totals[1], dir_depth[relative])
        add_top(entry)
    if errors:
        warnings.append(f"{errors} filesystem item(s) could not be read.")
    if depth_limited:
        warnings.append("Scan is depth-limited; directory totals may be incomplete.")
    entries = tuple(
        sorted(
            (item[2] for item in top_heap),
            key=lambda entry: (-entry.logical_bytes, entry.relative_path),
        )
    )
    ended = datetime.now(UTC)
    return ScanSummary(
        root=root,
        started_at=started,
        completed_at=ended,
        duration_seconds=max(0.0, time.monotonic() - clock),
        files_visited=files,
        directories_visited=directories,
        errors=errors,
        complete=complete and errors == 0 and not depth_limited,
        depth_limited=depth_limited,
        total_logical_bytes=total_logical_bytes,
        top_entries=entries,
        warnings=tuple(warnings),
    )
