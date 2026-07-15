from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


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


def run_install(
    home: Path,
    *args: str,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [bash_executable(), bash_path(INSTALL_SCRIPT), *args],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home), **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run_sourced(
    home: Path,
    body: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            bash_executable(),
            "-c",
            f'source "$1"; {body}',
            "atcode-test",
            bash_path(INSTALL_SCRIPT),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "HOME": str(home), **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


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

    install = run_install(home, "--launcher-only", env=env)

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


def test_unknown_install_option_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_install(home, "--unknown")

    assert result.returncode != 0
    assert "Usage:" in result.stderr


def test_launcher_only_does_not_edit_bashrc(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    bashrc = home / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")

    result = run_install(home, "--launcher-only")

    assert result.returncode == 0, result.stderr
    assert bashrc.read_text(encoding="utf-8") == "# existing\n"


def test_python_older_than_311_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    home.mkdir()
    fake_bin.mkdir()
    write_executable(
        fake_bin / "python3",
        "#!/usr/bin/env bash\nprintf 'Python 3.10.14\\n'\nexit 1\n",
    )

    result = run_sourced(
        home,
        "check_python",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode != 0
    assert "3.11" in result.stderr


def test_windows_mounted_codex_path_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_sourced(
        home,
        'is_windows_mounted_path "/mnt/c/nvm4w/nodejs/codex"',
    )

    assert result.returncode == 0


def test_codex_must_run_version_successfully(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    home.mkdir()
    fake_bin.mkdir()
    write_executable(fake_bin / "codex", "#!/usr/bin/env bash\nexit 1\n")

    result = run_sourced(
        home,
        "find_working_codex",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode != 0


def test_working_linux_codex_is_accepted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    home.mkdir()
    fake_bin.mkdir()
    write_executable(
        fake_bin / "codex",
        "#!/usr/bin/env bash\nprintf 'codex-cli test\\n'\n",
    )

    result = run_sourced(
        home,
        "find_working_codex",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr


def test_noninteractive_package_install_never_calls_sudo(tmp_path: Path) -> None:
    home = tmp_path / "home"
    fake_bin = tmp_path / "bin"
    home.mkdir()
    fake_bin.mkdir()
    write_executable(fake_bin / "apt-get", "#!/usr/bin/env bash\nexit 0\n")
    write_executable(
        fake_bin / "sudo",
        "#!/usr/bin/env bash\nprintf called > \"$HOME/sudo-called\"\n",
    )

    result = run_sourced(
        home,
        "install_apt_package tmux",
        env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode != 0
    assert not (home / "sudo-called").exists()


def test_shell_path_is_added_only_once(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    bashrc = home / ".bashrc"
    bashrc.write_text("# existing\n", encoding="utf-8")

    result = run_sourced(
        home,
        "confirm() { return 0; }; ensure_shell_path; ensure_shell_path",
    )

    assert result.returncode == 0, result.stderr
    assert bashrc.read_text(encoding="utf-8").splitlines().count(
        'export PATH="$HOME/.local/bin:$PATH"'
    ) == 1


def test_noninteractive_confirmation_is_denied(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_sourced(home, 'confirm "system change"')

    assert result.returncode != 0
