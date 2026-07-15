from pathlib import Path

from atcode.bootstrap import resolve_runtime_paths


def test_explicit_atcode_home_wins(tmp_path: Path) -> None:
    paths = resolve_runtime_paths(
        {"ATCODE_HOME": str(tmp_path)},
        Path("/opt/atcode"),
    )

    assert paths.home == tmp_path.resolve()
    assert paths.projects == tmp_path.resolve() / "projects"
    assert paths.global_config == tmp_path.resolve() / "config.json"


def test_default_home_is_install_root_data(tmp_path: Path) -> None:
    paths = resolve_runtime_paths({}, tmp_path)

    assert paths.home == (tmp_path / "data").resolve()


def test_relative_atcode_home_is_rejected(tmp_path: Path) -> None:
    try:
        resolve_runtime_paths({"ATCODE_HOME": "relative/data"}, tmp_path)
    except ValueError as error:
        assert "absolute" in str(error).lower()
    else:
        raise AssertionError("relative ATCODE_HOME must be rejected")
