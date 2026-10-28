from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_command(
    args: list[str],
    *,
    timeout: float,
    output_limit: int = 1_000_000,
) -> CommandResult:
    if not args or any(not isinstance(arg, str) for arg in args):
        raise ValueError("Command arguments must be a non-empty list of strings.")
    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Command timed out after {timeout:g} seconds.") from exc
    except OSError as exc:
        raise RuntimeError(f"Could not run {args[0]}: {exc}") from exc
    return CommandResult(
        completed.returncode,
        completed.stdout[:output_limit],
        completed.stderr[:output_limit],
    )
