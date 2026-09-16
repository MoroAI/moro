"""Exercise the installed command tree and local workflow without ML dependencies."""

import json

import pytest
from typer.testing import CliRunner

from moro.main import app
from moro.storage import db
from moro.training.hf_backend import HuggingFaceBackend

runner = CliRunner()


@pytest.mark.parametrize(
    "command",
    [
        [],
        ["init"],
        ["import"],
        ["status"],
        ["doctor"],
        ["data", "build"],
        ["data", "report"],
        ["recipe", "suggest"],
        ["train"],
        ["eval", "run"],
        ["eval", "report"],
        ["export"],
        ["deploy"],
        ["diagnose"],
    ],
)
def test_command_help(command):
    result = runner.invoke(app, [*command, "--help"])
    assert result.exit_code == 0, result.output


def build_project(tmp_path, sample_jsonl, monkeypatch):
    root = tmp_path / "demo"
    result = runner.invoke(app, ["init", str(root)])
    assert result.exit_code == 0, result.output
    monkeypatch.chdir(root)
    for command in (["import", str(sample_jsonl)], ["data", "build"]):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
    return root


def test_local_workflow(tmp_path, sample_jsonl, monkeypatch):
    root = build_project(tmp_path, sample_jsonl, monkeypatch)
    for command in (["status", "--json"], ["data", "report", "--format", "json"]):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, result.output
        assert isinstance(json.loads(result.output), dict)
    result = runner.invoke(app, ["import", str(root / "data/raw/support.jsonl")])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["train", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "Dry-run complete" in result.output
    assert not list((root / "runs").iterdir())


@pytest.mark.parametrize(
    "failure,code,status",
    [
        (RuntimeError("out of memory"), 1, "failed"),
        (KeyboardInterrupt(), 130, "cancelled"),
    ],
)
def test_training_failure_is_recorded(tmp_path, sample_jsonl, monkeypatch, failure, code, status):
    root = build_project(tmp_path, sample_jsonl, monkeypatch)

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(HuggingFaceBackend, "train", fail)
    result = runner.invoke(app, ["train"])
    assert result.exit_code == code, result.output
    conn = db.get_connection(root)
    try:
        row = conn.execute("SELECT * FROM runs").fetchone()
        assert row["status"] == status
        assert row["finished_at"]
        assert row["error"]
        from pathlib import Path

        output = Path(row["output_dir"])
        assert json.loads((output / "dataset.json").read_text())["sha256"]
        assert (output / "config.json").exists()
    finally:
        conn.close()


def test_resume_is_explicitly_unsupported(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project)
    result = runner.invoke(app, ["train", "--resume", "old-run"])
    assert result.exit_code == 2
    assert "not implemented" in result.output


def test_import_collision_preserves_existing_file(tmp_project, sample_jsonl, monkeypatch):
    monkeypatch.chdir(tmp_project)
    target = tmp_project / "data/raw/support.jsonl"
    target.write_text("keep this content")
    result = runner.invoke(app, ["import", str(sample_jsonl)])
    assert result.exit_code != 0
    assert target.read_text() == "keep this content"
