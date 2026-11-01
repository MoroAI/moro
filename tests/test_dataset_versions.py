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


def test_sdk_and_cli_share_absolute_relative_source_identity(tmp_project, sample_jsonl):
    import json

    from moro.config.loader import load_config
    from moro.data.compiler import DataCompiler
    from moro.data.versions import select_snapshot

    cfg = load_config(tmp_project / "moro.yaml")
    source = tmp_project / cfg.dataset.source
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(sample_jsonl.read_bytes())
    cfg.dataset.min_quality_score = 0
    (tmp_project / "moro.yaml").write_text(cfg.model_dump_json())
    version = DataCompiler(tmp_project).compile_dataset(source.resolve())
    assert select_snapshot(tmp_project, cfg)[0]["version_id"] == version
    assert (
        json.loads((tmp_project / "data/versions" / version / "manifest.json").read_text())[
            "dataset_version_id"
        ]
        == version
    )


def test_glossary_changes_invalidate_dataset_cache(tmp_project, sample_jsonl):
    from moro.cli.data import compile_project
    from moro.config.loader import load_config
    from moro.data.versions import select_snapshot

    cfg = load_config(tmp_project / "moro.yaml")
    source = tmp_project / cfg.dataset.source
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(sample_jsonl.read_bytes())
    cfg.dataset.min_quality_score = 0
    glossary = tmp_project / "domain_glossary.txt"
    glossary.write_text("first glossary")
    compile_project(tmp_project, cfg)
    assert select_snapshot(tmp_project, cfg)
    glossary.write_text("changed glossary")
    assert select_snapshot(tmp_project, cfg) is None


def test_splits_keep_duplicates_together_and_ignore_source_order():
    from moro.data.models import DatasetMessage, DatasetRow
    from moro.data.splitter import split_rows

    rows = [
        DatasetRow(
            id=str(i),
            source="fixture",
            messages=[
                DatasetMessage(role="user", content=f"question {i // 2}"),
                DatasetMessage(role="assistant", content=f"answer {i // 2}"),
            ],
        )
        for i in range(12)
    ]
    first = split_rows(rows, seed=7)
    second = split_rows(list(reversed(rows)), seed=7)
    assert [{r.id for r in split} for split in first] == [{r.id for r in split} for split in second]
    sets = [{r.messages[0].content for r in split} for split in first]
    assert not (sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])


def test_explicit_document_groups_stay_together_and_require_provenance():
    from moro.core.errors import DatasetError
    from moro.data.models import DatasetMessage, DatasetRow, DatasetRowMetadata
    from moro.data.splitter import split_rows

    rows = [
        DatasetRow(
            id=str(i),
            source="fixture",
            messages=[
                DatasetMessage(role="user", content=f"q{i}"),
                DatasetMessage(role="assistant", content=f"a{i}"),
            ],
            metadata=DatasetRowMetadata(group_id=f"document-{i // 3}"),
        )
        for i in range(12)
    ]
    splits = split_rows(rows, group_by="group_id")
    groups = [{r.metadata.group_id for r in split} for split in splits]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    rows[0].metadata.group_id = None
    with pytest.raises(DatasetError, match="group_id"):
        split_rows(rows, group_by="group_id")
