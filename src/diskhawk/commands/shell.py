from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

START_MARKER = "# >>> diskhawk shell integration >>>"
END_MARKER = "# <<< diskhawk shell integration <<<"


class ShellIntegrationError(ValueError):
    """Raised when shell integration cannot be modified safely."""


def startup_file(shell: str, home: Path | None = None) -> Path:
    directory = home or Path.home()
    if shell == "zsh":
        return directory / ".zshrc"
    if shell == "bash":
        return directory / ".bash_profile"
    raise ShellIntegrationError(f"Unsupported shell {shell!r}; supported shells are zsh and bash.")


def _integration_block(shell: str) -> str:
    if shell not in {"zsh", "bash"}:
        raise ShellIntegrationError(f"Unsupported shell {shell!r}.")
    filename = "zsh.zsh" if shell == "zsh" else "bash.bash"
    return (
        files("diskhawk")
        .joinpath("shell_integration", filename)
        .read_text(encoding="utf-8")
        .rstrip("\n")
    )


def _validate_shell(shell: str) -> None:
    if shell not in {"zsh", "bash"}:
        raise ShellIntegrationError(
            f"Unsupported shell {shell!r}; supported shells are zsh and bash."
        )


def _check_conflict(text: str, path_executable: str | None) -> None:
    if path_executable:
        raise ShellIntegrationError(
            f"A 'give' executable already exists at {path_executable}; "
            'use `diskhawk ask "give me disk info"` instead.'
        )
    existing_give = re.compile(
        r"(?m)^\s*(?:alias\s+give\s*=|(?:function\s+)?give\s*(?:\(\s*\))?\s*\{)"
    )
    if existing_give.search(text):
        raise ShellIntegrationError(
            "A 'give' alias or function already exists in the shell startup file; "
            'use `diskhawk ask "give me disk info"` instead.'
        )


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.diskhawk-{timestamp}.bak")
    suffix = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.diskhawk-{timestamp}-{suffix}.bak")
        suffix += 1
    shutil.copy2(path, backup)
    return backup


def install_shell_integration(
    shell: str,
    path: Path | None = None,
    *,
    home: Path | None = None,
) -> tuple[Path, Path | None]:
    _validate_shell(shell)
    target = path or startup_file(shell, home)
    current = target.read_text(encoding="utf-8") if target.exists() else ""
    if START_MARKER in current or END_MARKER in current:
        if current.count(START_MARKER) == 1 and current.count(END_MARKER) == 1:
            return target, None
        raise ShellIntegrationError(
            "The startup file contains an incomplete or duplicated DiskHawk block; no changes made."
        )
    conflict_text = current
    if path is None:
        shell_home = home or Path.home()
        other_files = (".zshenv", ".zprofile", ".zlogin") if shell == "zsh" else (".bashrc",)
        for filename in other_files:
            other = shell_home / filename
            if other != target and other.exists():
                conflict_text += "\n" + other.read_text(encoding="utf-8")
    _check_conflict(conflict_text, shutil.which("give"))
    backup = _backup(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not current or current.endswith("\n") else "\n"
    target.write_text(current + separator + _integration_block(shell) + "\n", encoding="utf-8")
    return target, backup


def uninstall_shell_integration(
    shell: str,
    path: Path | None = None,
    *,
    home: Path | None = None,
) -> tuple[Path, Path | None]:
    _validate_shell(shell)
    target = path or startup_file(shell, home)
    if not target.exists():
        raise ShellIntegrationError(f"Shell startup file does not exist: {target}")
    current = target.read_text(encoding="utf-8")
    if current.count(START_MARKER) != 1 or current.count(END_MARKER) != 1:
        raise ShellIntegrationError(
            "Expected exactly one complete DiskHawk integration block; no changes made."
        )
    pattern = re.compile(
        rf"(?m)^{re.escape(START_MARKER)}\n.*?^{re.escape(END_MARKER)}(?:\n|$)",
        re.DOTALL,
    )
    matches = list(pattern.finditer(current))
    if len(matches) != 1:
        raise ShellIntegrationError(
            "Expected exactly one complete DiskHawk integration block; no changes made."
        )
    backup = _backup(target)
    updated = current[: matches[0].start()] + current[matches[0].end() :]
    target.write_text(updated, encoding="utf-8")
    return target, backup
