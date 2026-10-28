from __future__ import annotations

import plistlib
import subprocess

import pytest

from diskhawk.core import disk_activity
from diskhawk.core.disk_activity import (
    _ActivityUnavailable,
    _Counters,
    _parse_ioreg_counters,
    sample_disk_activity,
)
from diskhawk.core.models import FilesystemInfo

_IOREG = """\
+-o IOBlockStorageDriver <class IOBlockStorageDriver, id 1>
  |   "Statistics" = {"Bytes (Read)"=1000,"Bytes (Write)"=2000}
  +-o APPLE SSD Media <class IOMedia, id 2>
    |   "BSD Name" = "disk0"
    +-o IOMediaBSDClient <class IOMediaBSDClient, id 3>
      |   "Statistics" = {"Bytes (Read)"=999999,"Bytes (Write)"=999999}
      |   "BSD Name" = "disk0s1"
+-o IOBlockStorageDriver <class IOBlockStorageDriver, id 4>
  |   "Statistics" = {"Bytes (Read)"=3000,"Bytes (Write)"=4000}
  +-o External Media <class IOMedia, id 5>
    |   "BSD Name" = "disk4"
"""


def _filesystem() -> FilesystemInfo:
    return FilesystemInfo("/Volumes/Test", 100, 40, 60, 40, source="/dev/disk3s5")


def test_ioreg_parser_uses_physical_driver_counters_only() -> None:
    assert _parse_ioreg_counters(_IOREG) == {
        "disk0": _Counters(1000, 2000),
        "disk4": _Counters(3000, 4000),
    }


def test_ioreg_parser_rejects_missing_counters() -> None:
    output = """\
+-o IOBlockStorageDriver <class IOBlockStorageDriver, id 1>
  |   "Statistics" = {"Operations (Read)"=4}
  +-o Storage Media <class IOMedia, id 2>
    |   "BSD Name" = "disk0"
"""
    with pytest.raises(_ActivityUnavailable, match="per-direction"):
        _parse_ioreg_counters(output)


def test_resolves_apfs_volumes_to_unique_physical_stores(monkeypatch) -> None:
    responses = iter(
        [
            {"APFSPhysicalStores": [{"APFSPhysicalStore": "disk0s2"}]},
            {"ParentWholeDisk": "disk0"},
            {"VirtualOrPhysical": "Physical"},
            {"APFSPhysicalStores": [{"APFSPhysicalStore": "disk0s3"}]},
            {"ParentWholeDisk": "disk0"},
        ]
    )
    commands: list[list[str]] = []

    def run_plist(arguments: list[str]) -> dict[str, object]:
        commands.append(arguments)
        return next(responses)

    monkeypatch.setattr(disk_activity, "_run_plist_command", run_plist)
    assert disk_activity._physical_devices([_filesystem(), _filesystem()]) == {"disk0"}
    assert len(commands) == 5


def test_virtual_disk_image_device_is_not_sampled(monkeypatch) -> None:
    responses = iter(
        [
            {"ParentWholeDisk": "disk9"},
            {"VirtualOrPhysical": "Virtual"},
        ]
    )
    monkeypatch.setattr(
        disk_activity,
        "_run_plist_command",
        lambda arguments: next(responses),
    )
    with pytest.raises(_ActivityUnavailable, match="disk-image"):
        disk_activity._physical_devices([_filesystem()])


def test_diskutil_plist_failures_are_reported(monkeypatch) -> None:
    monkeypatch.setattr(
        disk_activity.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("diskutil missing")),
    )
    with pytest.raises(_ActivityUnavailable, match="could not be queried"):
        disk_activity._run_plist_command(["diskutil", "info", "-plist", "/"])

    monkeypatch.setattr(
        disk_activity.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=b"invalid"),
    )
    with pytest.raises(_ActivityUnavailable, match="statistics were unavailable"):
        disk_activity._run_plist_command(["diskutil", "info", "-plist", "/"])

    monkeypatch.setattr(
        disk_activity.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=plistlib.dumps([])),
    )
    with pytest.raises(_ActivityUnavailable, match="statistics were unavailable"):
        disk_activity._run_plist_command(["diskutil", "info", "-plist", "/"])


def test_whole_disk_identifier_fallback_and_invalid_mapping() -> None:
    assert disk_activity._device_identifier({"Whole": True, "DeviceIdentifier": "disk8"}) == "disk8"
    with pytest.raises(_ActivityUnavailable, match="linked to a physical disk"):
        disk_activity._device_identifier({"DeviceIdentifier": "not-a-disk"})


def test_malformed_apfs_physical_stores_are_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        disk_activity,
        "_run_plist_command",
        lambda arguments: {"APFSPhysicalStores": []},
    )
    with pytest.raises(_ActivityUnavailable, match="no physical store"):
        disk_activity._physical_devices([_filesystem()])

    monkeypatch.setattr(
        disk_activity,
        "_run_plist_command",
        lambda arguments: {"APFSPhysicalStores": [{}]},
    )
    with pytest.raises(_ActivityUnavailable, match="physical store is unavailable"):
        disk_activity._physical_devices([_filesystem()])


def _sample_with_snapshots(monkeypatch, snapshots, *, times=(10.0, 10.0, 11.0, 11.0)):
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    monkeypatch.setattr(disk_activity, "_physical_devices", lambda rows: {"disk0"})
    readings = iter(snapshots)
    monkeypatch.setattr(disk_activity, "_snapshot", lambda devices: next(readings))
    clock_values = iter(times)
    monkeypatch.setattr(disk_activity.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(disk_activity.time, "sleep", lambda duration: None)
    return sample_disk_activity([_filesystem()])


def test_calculates_independent_read_and_write_rates(monkeypatch) -> None:
    activity = _sample_with_snapshots(
        monkeypatch,
        [
            {"disk0": _Counters(1000, 5000)},
            {"disk0": _Counters(6000, 15_000)},
        ],
    )
    assert activity.read_bytes_per_second == 5000
    assert activity.write_bytes_per_second == 10_000


def test_rates_use_measured_elapsed_interval(monkeypatch) -> None:
    activity = _sample_with_snapshots(
        monkeypatch,
        [
            {"disk0": _Counters(10_000, 20_000)},
            {"disk0": _Counters(35_000, 60_000)},
        ],
        times=(5.0, 5.0, 7.5, 7.5),
    )
    assert activity.read_bytes_per_second == 10_000
    assert activity.write_bytes_per_second == 16_000
    assert "2.50 s" in activity.status


def test_rates_aggregate_distinct_physical_devices(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    monkeypatch.setattr(disk_activity, "_physical_devices", lambda rows: {"disk0", "disk4"})
    snapshots = iter(
        [
            {"disk0": _Counters(100, 200), "disk4": _Counters(300, 400)},
            {"disk0": _Counters(1100, 1200), "disk4": _Counters(2300, 2400)},
        ]
    )
    monkeypatch.setattr(disk_activity, "_snapshot", lambda devices: next(snapshots))
    clock_values = iter((0.0, 0.0, 2.0, 2.0))
    monkeypatch.setattr(disk_activity.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(disk_activity.time, "sleep", lambda duration: None)

    activity = sample_disk_activity([_filesystem()])
    assert activity.read_bytes_per_second == 1500
    assert activity.write_bytes_per_second == 1500


def test_zero_counter_delta_is_a_valid_zero_activity_sample(monkeypatch) -> None:
    activity = _sample_with_snapshots(
        monkeypatch,
        [
            {"disk0": _Counters(10, 20)},
            {"disk0": _Counters(10, 20)},
        ],
    )
    assert activity.read_bytes_per_second == 0
    assert activity.write_bytes_per_second == 0


def test_counter_reset_marks_only_affected_direction_unavailable(monkeypatch) -> None:
    activity = _sample_with_snapshots(
        monkeypatch,
        [
            {"disk0": _Counters(100, 200)},
            {"disk0": _Counters(50, 500)},
        ],
    )
    assert activity.read_bytes_per_second is None
    assert activity.write_bytes_per_second == 300
    assert "Counter reset" in activity.status


def test_unsupported_platform_returns_unavailable_without_sampling(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "linux")
    monkeypatch.setattr(
        disk_activity.time,
        "sleep",
        lambda duration: pytest.fail("unsupported platform must not wait"),
    )
    activity = sample_disk_activity([_filesystem()])
    assert activity.read_bytes_per_second is None
    assert activity.write_bytes_per_second is None
    assert "require macOS" in activity.status


def test_invalid_interval_and_zero_elapsed_are_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    invalid = sample_disk_activity([_filesystem()], interval_seconds=0)
    assert invalid.read_bytes_per_second is None
    assert "invalid sampling interval" in invalid.status

    monkeypatch.setattr(disk_activity, "_physical_devices", lambda rows: {"disk0"})
    snapshots = iter(
        [
            {"disk0": _Counters(100, 200)},
            {"disk0": _Counters(200, 300)},
        ]
    )
    monkeypatch.setattr(disk_activity, "_snapshot", lambda devices: next(snapshots))
    clock_values = iter((1.0, 1.0, 1.0, 1.0))
    monkeypatch.setattr(disk_activity.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(disk_activity.time, "sleep", lambda duration: None)
    zero_elapsed = sample_disk_activity([_filesystem()])
    assert zero_elapsed.read_bytes_per_second is None
    assert "interval was invalid" in zero_elapsed.status


def test_missing_device_in_second_snapshot_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    monkeypatch.setattr(disk_activity, "_physical_devices", lambda rows: {"disk0"})
    snapshots = iter(
        [
            {"disk0": _Counters(100, 200)},
            {},
        ]
    )
    monkeypatch.setattr(disk_activity, "_ioreg_counters", lambda: next(snapshots))
    monkeypatch.setattr(disk_activity.time, "sleep", lambda duration: None)
    activity = sample_disk_activity([_filesystem()])
    assert activity.read_bytes_per_second is None
    assert "disappeared" in activity.status


def test_ioreg_command_failure_is_a_clear_unavailable_result(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    monkeypatch.setattr(disk_activity, "_physical_devices", lambda rows: {"disk0"})
    monkeypatch.setattr(
        disk_activity,
        "_snapshot",
        lambda devices: (_ for _ in ()).throw(_ActivityUnavailable("device removed")),
    )
    activity = sample_disk_activity([_filesystem()])
    assert activity.read_bytes_per_second is None
    assert "device removed" in activity.status


def test_mapping_command_failures_do_not_fake_activity(monkeypatch) -> None:
    monkeypatch.setattr(disk_activity.sys, "platform", "darwin")
    monkeypatch.setattr(
        disk_activity,
        "_run_plist_command",
        lambda arguments: (_ for _ in ()).throw(
            _ActivityUnavailable("macOS disk statistics could not be queried")
        ),
    )
    activity = sample_disk_activity([_filesystem()])
    assert activity.read_bytes_per_second is None
    assert "could not be queried" in activity.status


def test_ioreg_subprocess_errors_are_normalized(monkeypatch) -> None:
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(disk_activity.subprocess, "run", run)
    with pytest.raises(_ActivityUnavailable, match="IOKit"):
        disk_activity._ioreg_counters()
