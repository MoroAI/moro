from pathlib import Path

import pytest

from moro.core.errors import ExportError
from moro.export import manifest


@pytest.fixture
def run(tmp_path: Path) -> Path:
    root = tmp_path / "run"
    adapter = root / "adapter"
    adapter.mkdir(parents=True)
    (adapter / "weights.bin").write_bytes(b"original adapter")
    return root


@pytest.mark.parametrize("location", ["same", "inside", "ancestor", "alias"])
def test_export_rejects_overlapping_paths(run: Path, location: str):
    if location == "same":
        output = run
    elif location == "inside":
        output = run / "adapter" / "release"
    elif location == "ancestor":
        nested_run = run / "adapter" / "nested"
        (nested_run / "adapter").mkdir(parents=True)
        (nested_run / "adapter" / "weights.bin").write_bytes(b"nested")
        output, run = run, nested_run
    else:
        output = run.parent / "alias"
        output.symlink_to(run, target_is_directory=True)
    original = (run / "adapter" / "weights.bin").read_bytes()
    with pytest.raises(ExportError, match="overlap"):
        manifest.export_adapter(run, output)
    assert (run / "adapter" / "weights.bin").read_bytes() == original


def test_export_preserves_existing_destination(run: Path):
    output = run.parent / "release"
    (output / "adapter").mkdir(parents=True)
    (output / "adapter" / "old.bin").write_bytes(b"previous export")
    with pytest.raises(ExportError, match="already exists"):
        manifest.export_adapter(run, output)
    assert (output / "adapter" / "old.bin").read_bytes() == b"previous export"


def test_export_rejects_dangling_destination_link(run: Path):
    output = run.parent / "release"
    output.mkdir()
    (output / "adapter").symlink_to(output / "missing", target_is_directory=True)
    with pytest.raises(ExportError, match="already exists"):
        manifest.export_adapter(run, output)
    assert (output / "adapter").is_symlink()


def test_failed_copy_does_not_publish_partial_adapter(run: Path, monkeypatch):
    output = run.parent / "release"

    def fail_copy(source, destination, **kwargs):
        Path(destination).mkdir()
        (Path(destination) / "partial.bin").write_bytes(b"partial")
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(manifest.shutil, "copytree", fail_copy)
    with pytest.raises(ExportError, match="synthetic disk failure"):
        manifest.export_adapter(run, output)
    assert not (output / "adapter").exists()
    assert list(output.iterdir()) == []
    assert (run / "adapter" / "weights.bin").read_bytes() == b"original adapter"


def test_export_copies_to_independent_directory(run: Path):
    output = run.parent / "release"
    destination = manifest.export_adapter(run, output)
    assert destination == output / "adapter"
    assert (destination / "weights.bin").read_bytes() == b"original adapter"
    (destination / "weights.bin").write_bytes(b"changed export")
    assert (run / "adapter" / "weights.bin").read_bytes() == b"original adapter"
    assert list(output.iterdir()) == [destination]


def test_export_rejects_source_symlink_entries(run: Path):
    (run / "adapter" / "recursive").symlink_to(run / "adapter", target_is_directory=True)
    with pytest.raises(ExportError, match="symbolic link"):
        manifest.export_adapter(run, run.parent / "release")


def test_export_requires_source_directory(tmp_path: Path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "adapter").write_text("not a directory")
    with pytest.raises(ExportError, match="directory"):
        manifest.export_adapter(run, tmp_path / "release")
