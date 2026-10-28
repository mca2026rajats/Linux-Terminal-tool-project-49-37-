from __future__ import annotations

import plistlib
import re
import subprocess
import sys
import time
from dataclasses import dataclass

from diskhawk.core.models import FilesystemInfo

_COMMAND_TIMEOUT_SECONDS = 5
_SAMPLE_INTERVAL_SECONDS = 1.0
_DEVICE_IDENTIFIER = re.compile(r"disk[0-9]+")
_DRIVER_HEADER = re.compile(
    r"^[ |]*\+-o IOBlockStorageDriver\s+<class IOBlockStorageDriver,", re.MULTILINE
)
_NODE_HEADER = re.compile(r"^[ |]*\+-o ", re.MULTILINE)
_COUNTER = re.compile(r'"Bytes \((Read|Write)\)"\s*=\s*(\d+)')
_BSD_NAME = re.compile(r'"BSD Name"\s*=\s*"(?P<name>disk[0-9]+)"')


@dataclass(frozen=True)
class DiskActivity:
    read_bytes_per_second: float | None
    write_bytes_per_second: float | None
    status: str


@dataclass(frozen=True)
class _Counters:
    read_bytes: int | None
    write_bytes: int | None


class _ActivityUnavailable(Exception):
    pass


def _run_plist_command(arguments: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ActivityUnavailable("macOS disk statistics could not be queried") from exc
    try:
        payload = plistlib.loads(result.stdout)
    except (plistlib.InvalidFileException, ValueError, TypeError) as exc:
        raise _ActivityUnavailable("macOS disk statistics were unavailable") from exc
    if not isinstance(payload, dict):
        raise _ActivityUnavailable("macOS disk statistics were unavailable")
    return payload


def _device_identifier(info: dict[str, object]) -> str:
    parent = info.get("ParentWholeDisk")
    if isinstance(parent, str) and _DEVICE_IDENTIFIER.fullmatch(parent):
        return parent
    if info.get("Whole") is True:
        device = info.get("DeviceIdentifier")
        if isinstance(device, str) and _DEVICE_IDENTIFIER.fullmatch(device):
            return device
    raise _ActivityUnavailable("the selected volume could not be linked to a physical disk")


def _require_nonvirtual_device(device: str) -> None:
    info = _run_plist_command(["diskutil", "info", "-plist", f"/dev/{device}"])
    if str(info.get("VirtualOrPhysical", "")).casefold() == "virtual":
        raise _ActivityUnavailable("virtual or disk-image devices are not measured")


def _physical_devices(filesystems: list[FilesystemInfo]) -> set[str]:
    devices: set[str] = set()
    for filesystem in filesystems:
        target = filesystem.source or filesystem.mount_point
        info = _run_plist_command(["diskutil", "info", "-plist", target])
        stores = info.get("APFSPhysicalStores")
        if isinstance(stores, list):
            if not stores:
                raise _ActivityUnavailable("the selected APFS volume has no physical store")
            for entry in stores:
                if not isinstance(entry, dict):
                    raise _ActivityUnavailable("the selected APFS physical store is unavailable")
                store = entry.get("APFSPhysicalStore")
                if not isinstance(store, str) or not store:
                    raise _ActivityUnavailable("the selected APFS physical store is unavailable")
                store_info = _run_plist_command(["diskutil", "info", "-plist", f"/dev/{store}"])
                device = _device_identifier(store_info)
                if device not in devices:
                    _require_nonvirtual_device(device)
                    devices.add(device)
        else:
            device = _device_identifier(info)
            if device not in devices:
                _require_nonvirtual_device(device)
                devices.add(device)
    if not devices:
        raise _ActivityUnavailable("no physical storage devices were identified")
    return devices


def _parse_ioreg_counters(output: str) -> dict[str, _Counters]:
    lines = output.splitlines()
    driver_indexes = [index for index, line in enumerate(lines) if _DRIVER_HEADER.match(line)]
    if not driver_indexes:
        raise _ActivityUnavailable("IOKit per-direction disk counters are unavailable")

    devices: dict[str, _Counters] = {}
    for line_index in driver_indexes:
        child_index = next(
            (
                index
                for index in range(line_index + 1, len(lines))
                if _NODE_HEADER.match(lines[index])
            ),
            len(lines),
        )
        driver_properties = "\n".join(lines[line_index + 1 : child_index])
        counter_values = {
            direction: int(value) for direction, value in _COUNTER.findall(driver_properties)
        }
        if "Read" not in counter_values or "Write" not in counter_values:
            continue
        if child_index == len(lines):
            continue
        next_child = next(
            (
                index
                for index in range(child_index + 1, len(lines))
                if _NODE_HEADER.match(lines[index])
            ),
            len(lines),
        )
        child_properties = "\n".join(lines[child_index + 1 : next_child])
        bsd_name = _BSD_NAME.search(child_properties)
        if bsd_name is None:
            continue
        devices[bsd_name.group("name")] = _Counters(
            counter_values["Read"],
            counter_values["Write"],
        )
    if not devices:
        raise _ActivityUnavailable("IOKit per-direction disk counters are unavailable")
    return devices


def _ioreg_counters() -> dict[str, _Counters]:
    try:
        result = subprocess.run(
            ["ioreg", "-r", "-c", "IOBlockStorageDriver", "-l", "-w0"],
            check=True,
            capture_output=True,
            text=True,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise _ActivityUnavailable("IOKit per-direction disk counters are unavailable") from exc
    return _parse_ioreg_counters(result.stdout)


def _snapshot(devices: set[str]) -> dict[str, _Counters]:
    available = _ioreg_counters()
    missing = devices - available.keys()
    if missing:
        raise _ActivityUnavailable("a selected physical disk disappeared or has no IOKit counters")
    return {device: available[device] for device in devices}


def _rate(
    before: dict[str, _Counters],
    after: dict[str, _Counters],
    elapsed_seconds: float,
    direction: str,
) -> float | None:
    field = "read_bytes" if direction == "Read" else "write_bytes"
    differences: list[int] = []
    for device, initial in before.items():
        start = getattr(initial, field)
        end = getattr(after[device], field)
        if start is None or end is None or end < start:
            return None
        differences.append(end - start)
    return sum(differences) / elapsed_seconds


def sample_disk_activity(
    filesystems: list[FilesystemInfo],
    *,
    interval_seconds: float = _SAMPLE_INTERVAL_SECONDS,
) -> DiskActivity:
    """Measure separate physical read/write throughput from macOS IOKit counters."""
    if sys.platform != "darwin":
        return DiskActivity(None, None, "N/A: live IOKit counters require macOS")
    if interval_seconds <= 0:
        return DiskActivity(None, None, "N/A: invalid sampling interval")

    try:
        devices = _physical_devices(filesystems)
        before_started = time.monotonic()
        before = _snapshot(devices)
        before_finished = time.monotonic()
    except _ActivityUnavailable as exc:
        return DiskActivity(None, None, f"N/A: {exc}")

    time.sleep(interval_seconds)
    try:
        after_started = time.monotonic()
        after = _snapshot(devices)
        after_finished = time.monotonic()
    except _ActivityUnavailable as exc:
        return DiskActivity(None, None, f"N/A: {exc}")
    elapsed_seconds = ((after_started + after_finished) - (before_started + before_finished)) / 2
    if elapsed_seconds <= 0:
        return DiskActivity(None, None, "N/A: measured sampling interval was invalid")

    read_rate = _rate(before, after, elapsed_seconds, "Read")
    write_rate = _rate(before, after, elapsed_seconds, "Write")
    unavailable_directions = [
        direction
        for direction, rate in (("read", read_rate), ("write", write_rate))
        if rate is None
    ]
    status = (
        f"Counter reset; {', '.join(unavailable_directions)} speed unavailable. "
        if unavailable_directions
        else ""
    )
    return DiskActivity(
        read_rate,
        write_rate,
        f"{status}Physical-device throughput measured over {elapsed_seconds:.2f} s; "
        "not benchmark performance.",
    )
