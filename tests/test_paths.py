"""Tests for path helpers."""

from pathlib import Path

from moro.core.paths import (
    ensure_project_dirs,
    find_project_root,
    project_dirs,
)


def test_find_project_root_finds_config(tmp_project: Path):
    assert find_project_root(tmp_project) == tmp_project


def test_find_project_root_from_subdir(tmp_project: Path):
    subdir = tmp_project / "data" / "raw"
    assert find_project_root(subdir) == tmp_project


def test_find_project_root_returns_none_outside(tmp_path: Path):
    assert find_project_root(tmp_path) is None


def test_project_dirs_keys(tmp_project: Path):
    dirs = project_dirs(tmp_project)
    expected = {
        "root",
        "moro",
        "artifacts",
        "logs",
        "reports",
        "data",
        "raw",
        "normalized",
        "splits",
        "eval",
        "runs",
        "releases",
    }
    assert expected.issubset(set(dirs.keys()))


def test_ensure_project_dirs_creates_all(tmp_path: Path):
    root = tmp_path / "new-project"
    dirs = ensure_project_dirs(root)
    for path in dirs.values():
        assert path.exists(), f"Expected {path} to exist"
