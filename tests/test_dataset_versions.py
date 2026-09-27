import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from moro.main import app
from moro.storage import db
from moro.training.hf_backend import HuggingFaceBackend

runner = CliRunner()


@pytest.fixture
def built(tmp_project, monkeypatch, sample_jsonl):
    monkeypatch.chdir(tmp_project)
    for args in (["import", str(sample_jsonl)], ["data", "build"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
    return tmp_project


def versions(root):
    conn = db.get_connection(root)
    rows = conn.execute("SELECT * FROM dataset_versions ORDER BY created_at, id").fetchall()
    conn.close()
    return rows


def test_rebuild_preserves_old_versions_and_force_has_effect(built):
    first = versions(built)[0]
    path = built / first["normalized_path"]
    original = path.read_bytes()
    result = runner.invoke(app, ["data", "build"])
    assert result.exit_code == 0
    assert len(versions(built)) == 1
    result = runner.invoke(app, ["data", "build", "--force"])
    assert result.exit_code == 0, result.output
    assert len(versions(built)) == 2
    assert path.read_bytes() == original
    assert versions(built)[1]["normalized_path"] != first["normalized_path"]


def test_source_attribution_uses_configured_file(built, tmp_path):
    other = tmp_path / "other.jsonl"
    other.write_text('{"prompt":"x","completion":"y"}\n')
    assert runner.invoke(app, ["import", str(other)]).exit_code == 0
    assert runner.invoke(app, ["data", "build", "--force"]).exit_code == 0
    conn = db.get_connection(built)
    row = conn.execute(
        "SELECT s.path FROM dataset_versions v JOIN dataset_sources s ON s.id=v.source_id "
        "ORDER BY v.created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert Path(row["path"]).name == "support.jsonl"


def test_tampered_split_blocks_training(built):
    split = (built / versions(built)[0]["normalized_path"]).parent / "train.jsonl"
    split.write_text(split.read_text() + "\n")
    result = runner.invoke(app, ["train", "--dry-run"])
    assert result.exit_code == 5
    assert "integrity failure" in result.output


def test_run_is_bound_and_honors_output_directory(built, monkeypatch):
    path = built / "moro.yaml"
    config = yaml.safe_load(path.read_text())
    config["training"]["output_dir"] = "custom-runs"
    path.write_text(yaml.safe_dump(config))
    monkeypatch.setattr(HuggingFaceBackend, "train", lambda self, **kwargs: {"train_loss": 0.2})
    result = runner.invoke(app, ["train"])
    assert result.exit_code == 0, result.output
    conn = db.get_connection(built)
    run = conn.execute("SELECT * FROM runs").fetchone()
    conn.close()
    assert run["dataset_version_id"] == versions(built)[0]["id"]
    assert Path(run["output_dir"]).parent == built / "custom-runs"
    report = json.loads((Path(run["output_dir"]) / "dataset.json").read_text())
    assert report["manifest_sha256"]


@pytest.mark.parametrize("option,value", [("validation_ratio", 0.5), ("batch_sze", 3)])
def test_strict_configuration_rejects_bad_settings(tmp_project, monkeypatch, option, value):
    monkeypatch.chdir(tmp_project)
    path = tmp_project / "moro.yaml"
    config = yaml.safe_load(path.read_text())
    if option == "validation_ratio":
        config["dataset"].update(validation_ratio=0.5, eval_ratio=0.5)
    else:
        config["training"][option] = value
    path.write_text(yaml.safe_dump(config))
    assert runner.invoke(app, ["data", "build"]).exit_code != 0


def test_limit_stops_jsonl_before_later_invalid_record(tmp_path):
    from moro.data.ingest import read_raw_rows

    path = tmp_path / "limited.jsonl"
    path.write_text('{"prompt":"x","completion":"y"}\ninvalid\n')
    assert len(read_raw_rows(path, limit=1)) == 1


def test_tiny_split_rejected():
    from moro.core.errors import DatasetError
    from moro.data.splitter import split_rows

    with pytest.raises(DatasetError, match="at least"):
        split_rows([object()])
