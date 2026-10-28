from __future__ import annotations

from pathlib import Path

import pytest

from diskhawk.commands.shell import (
    ShellIntegrationError,
    install_shell_integration,
    startup_file,
    uninstall_shell_integration,
)


def test_shell_install_is_idempotent_and_backed_up(tmp_path: Path) -> None:
    startup = tmp_path / ".zshrc"
    startup.write_text("export PATH=/bin\n", encoding="utf-8")
    target, backup = install_shell_integration("zsh", startup)
    assert target == startup
    assert backup is not None and backup.read_text() == "export PATH=/bin\n"
    first = startup.read_text()
    install_shell_integration("zsh", startup)
    assert startup.read_text() == first
    assert first.count("give()") == 1
    removed_target, removed_backup = uninstall_shell_integration("zsh", startup)
    assert removed_target == startup
    assert removed_backup is not None
    assert startup.read_text() == "export PATH=/bin\n"


def test_shell_conflicts_and_invalid_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    startup = tmp_path / ".bashrc"
    startup.write_text("alias give='some-command'\n", encoding="utf-8")
    monkeypatch.setattr("diskhawk.commands.shell.shutil.which", lambda name: None)
    with pytest.raises(ShellIntegrationError, match="already exists"):
        install_shell_integration("bash", startup)
    startup.write_text("give() { echo existing; }\n", encoding="utf-8")
    with pytest.raises(ShellIntegrationError):
        install_shell_integration("bash", startup)
    startup.write_text("", encoding="utf-8")
    with pytest.raises(ShellIntegrationError, match="Unsupported"):
        install_shell_integration("fish", startup)
    with pytest.raises(ShellIntegrationError, match="exactly one"):
        uninstall_shell_integration("bash", startup)


def test_shell_detects_path_conflict_and_removes_only_managed_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    startup = tmp_path / ".zshrc"
    monkeypatch.setattr("diskhawk.commands.shell.shutil.which", lambda name: "/usr/bin/give")
    with pytest.raises(ShellIntegrationError, match="executable"):
        install_shell_integration("zsh", startup)
    monkeypatch.setattr("diskhawk.commands.shell.shutil.which", lambda name: None)
    startup.write_text("before\n", encoding="utf-8")
    install_shell_integration("zsh", startup)
    with startup.open("a", encoding="utf-8") as file:
        file.write("after\n")
    uninstall_shell_integration("zsh", startup)
    assert startup.read_text() == "before\nafter\n"


def test_bash_checks_both_startup_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("diskhawk.commands.shell.shutil.which", lambda name: None)
    (tmp_path / ".bashrc").write_text("give() { echo existing; }\n", encoding="utf-8")
    assert startup_file("bash", tmp_path) == tmp_path / ".bash_profile"
    with pytest.raises(ShellIntegrationError, match="already exists"):
        install_shell_integration("bash", home=tmp_path)
