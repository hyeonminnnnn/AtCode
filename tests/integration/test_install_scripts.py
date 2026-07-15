from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def bash_executable() -> str:
    if os.name == "nt":
        return r"C:\Program Files\Git\bin\bash.exe"
    return "/bin/bash"


def bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return str(resolved)
    drive = resolved.drive.removesuffix(":").lower()
    remainder = resolved.as_posix()[2:]
    return f"/{drive}{remainder}"


def test_install_and_uninstall_preserve_runtime_data(tmp_path: Path) -> None:
    home = tmp_path / "home"
    runtime_home = tmp_path / "runtime"
    home.mkdir()
    runtime_home.mkdir()
    marker = runtime_home / "keep-me"
    marker.write_text("keep", encoding="utf-8")
    env = {
        **os.environ,
        "HOME": str(home),
        "ATCODE_HOME": str(runtime_home),
        "ATCODE_PYTHON": sys.executable,
    }

    install = subprocess.run(
        [
            bash_executable(),
            "-c",
            'PATH=/usr/bin:/bin; export PATH; exec "$1"',
            "atcode-test",
            bash_path(REPO_ROOT / "scripts" / "install.sh"),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert install.returncode == 0, install.stderr
    command = home / ".local" / "bin" / "atcode"
    assert command.exists()

    help_result = subprocess.run(
        [
            bash_executable(),
            "-c",
            'PATH=/usr/bin:/bin; export PATH; exec "$1" --help',
            "atcode-test",
            bash_path(command),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "usage: atcode" in help_result.stdout

    uninstall = subprocess.run(
        [
            bash_executable(),
            "-c",
            'PATH=/usr/bin:/bin; export PATH; exec "$1"',
            "atcode-test",
            bash_path(REPO_ROOT / "scripts" / "uninstall.sh"),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert uninstall.returncode == 0, uninstall.stderr
    assert not command.exists()
    assert marker.exists()
