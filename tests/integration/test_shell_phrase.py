from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from diskhawk.commands.shell import install_shell_integration


def test_exact_phrase_in_isolated_zsh(tmp_path: Path) -> None:
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("zsh is not installed")
    startup = tmp_path / ".zshrc"
    install_shell_integration("zsh", startup)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    command = f"source {shlex.quote(str(startup))}; give me disk info"
    result = subprocess.run(
        [zsh, "-f", "-c", command],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DISKHAWK" in result.stdout
    assert "available" in result.stdout


def test_exact_phrase_in_isolated_bash(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    startup = tmp_path / ".bash_profile"
    install_shell_integration("bash", startup)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}",
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
    }
    command = f"source {shlex.quote(str(startup))}; give me disk info"
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", command],
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DISKHAWK" in result.stdout
    assert "available" in result.stdout
