import json

import pytest
import yaml
from typer.testing import CliRunner

from moro.config.loader import load_config
from moro.core.hashing import sha256_text
from moro.main import app
from moro.storage import db

runner = CliRunner()


@pytest.mark.parametrize("rate", [1e-5, 1e-6])
def test_unchanged_scientific_notation_snapshot_can_export(recorded_run, rate):
    root, directory, run, config = recorded_run
    config.training.learning_rate = rate
    (directory / "config.json").write_text(config.model_dump_json(indent=2))
    conn = db.get_connection(root)
    conn.execute("UPDATE runs SET config_hash = ? WHERE id = ?",
                 (sha256_text(config.model_dump_json()), run))
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("tag", ["../../../../escaped", "a/b", "a\\b", ".", "..", "", "a b",
                                 "a\nb", "/absolute", "x" * 129])
def test_unsafe_deployment_tags_rejected(recorded_run, tag):
    root, _, run, _ = recorded_run
    result = runner.invoke(app, ["deploy", "--run-id", run, "--tag", tag])
    assert result.exit_code == 1, result.output
    assert "tag" in result.output.lower()
    assert not list((root / "releases").iterdir())


def test_deployment_refuses_symlinked_package_directory(recorded_run, tmp_path):
    root, _, run, _ = recorded_run
    outside = tmp_path / "outside"
    outside.mkdir()
    output = root / "releases" / f"{run}_v1"
    output.mkdir()
    (output / "ollama_package").symlink_to(outside, target_is_directory=True)
    result = runner.invoke(app, ["deploy", "--run-id", run, "--tag", "v1"])
    assert result.exit_code == 1
    assert not list(outside.iterdir())


@pytest.mark.parametrize("tag", ["v0.1.0", "release_1", "candidate-2"])
def test_valid_deployment_tags(recorded_run, tag):
    root, _, run, _ = recorded_run
    result = runner.invoke(app, ["deploy", "--run-id", run, "--tag", tag])
    assert result.exit_code == 0, result.output
    assert (root / "releases" / f"{run}_{tag}" / "ollama_package/Modelfile").is_file()


@pytest.fixture
def recorded_run(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project)
    project_file = tmp_project / "moro.yaml"
    project_file.write_text(
        project_file.read_text().replace("safety_pass: true", "safety_pass: false")
    )
    config = load_config(project_file)
    config.model.revision = "recorded-revision"
    directory = tmp_project / "runs" / "fixture"
    adapter = directory / "adapter"
    adapter.mkdir(parents=True)
    (directory / "config.json").write_text(config.model_dump_json(indent=2))
    (adapter / "adapter_config.json").write_text(json.dumps({"peft_type": "LORA", "r": 16}))
    # Structural fixture only: these bytes do not represent loadable tensors.
    (adapter / "adapter_model.safetensors").write_bytes(b"synthetic weights")
    conn = db.get_connection(tmp_project)
    project = db.get_or_create_project(conn, config.project.name)
    run = db.create_run(
        conn,
        project,
        sha256_text(config.model_dump_json()),
        config.model.name,
        config.model.quantization,
        str(directory),
    )
    db.update_run_status(conn, run, "completed")
    conn.close()
    return tmp_project, directory, run, config


@pytest.mark.parametrize("command", [["export"], ["export", "--format", "ollama"], ["deploy"]])
@pytest.mark.parametrize("status", ["pending", "running", "failed", "cancelled"])
def test_unfinished_runs_cannot_export(recorded_run, command, status):
    root, directory, run, _ = recorded_run
    conn = db.get_connection(root)
    db.update_run_status(conn, run, status)
    conn.close()
    result = runner.invoke(app, [*command, "--run-id", run])
    assert result.exit_code == 1
    assert "requires a completed run" in " ".join(result.output.split())
    assert not list((root / "releases").iterdir())
    assert (directory / "adapter/adapter_model.safetensors").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "snapshot_missing",
        "snapshot_changed",
        "config_missing",
        "config_invalid",
        "weights_missing",
        "weights_empty",
    ],
)
@pytest.mark.parametrize("command", ["export", "deploy"])
def test_incomplete_artifacts_fail_before_publication(recorded_run, damage, command):
    root, directory, run, config = recorded_run
    snapshot = directory / "config.json"
    metadata = directory / "adapter/adapter_config.json"
    weights = directory / "adapter/adapter_model.safetensors"
    if damage == "snapshot_missing":
        snapshot.unlink()
    elif damage == "snapshot_changed":
        config.model.name = "different-model"
        snapshot.write_text(config.model_dump_json())
    elif damage == "config_missing":
        metadata.unlink()
    elif damage == "config_invalid":
        metadata.write_text("[]")
    elif damage == "weights_missing":
        weights.unlink()
    else:
        weights.write_bytes(b"")
    result = runner.invoke(app, [command, "--run-id", run])
    assert result.exit_code == 1, result.output
    assert "Export error" in result.output
    assert "Unexpected error" not in result.output
    assert not list((root / "releases").iterdir())


@pytest.mark.parametrize("command", [["export"], ["export", "--format", "ollama"], ["deploy"]])
def test_exports_use_snapshot_after_project_model_changes(recorded_run, command):
    root, _, run, config = recorded_run
    project_file = root / "moro.yaml"
    project_file.write_text(project_file.read_text().replace(config.model.name, "changed/current"))
    result = runner.invoke(app, [*command, "--run-id", run])
    assert result.exit_code == 0, result.output
    if command == ["export"]:
        manifest = json.loads((root / "releases" / run / "manifest.json").read_text())
        assert manifest["base_model"] == config.model.name
        assert manifest["base_model_revision"] == "recorded-revision"
        assert config.model.name in (root / "releases" / run / "model_card.md").read_text()
    else:
        modelfile = next((root / "releases").rglob("Modelfile")).read_text()
        assert f"FROM {config.model.name}\n" in modelfile
        assert "changed/current" not in modelfile


def test_default_selection_ignores_newer_failed_run(recorded_run):
    root, _, run, config = recorded_run
    conn = db.get_connection(root)
    project = db.get_or_create_project(conn, config.project.name)
    failed = db.create_run(conn, project, "unused", "unused", "none", "missing")
    db.update_run_status(conn, failed, "failed")
    conn.close()
    result = runner.invoke(app, ["export"])
    assert result.exit_code == 0, result.output
    assert (root / "releases" / run / "manifest.json").exists()


def test_explicit_run_must_belong_to_project(recorded_run):
    root, _, run, _ = recorded_run
    conn = db.get_connection(root)
    other = db.get_or_create_project(conn, "other")
    conn.execute("UPDATE runs SET project_id = ? WHERE id = ?", (other, run))
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "No matching completed run" in result.output
    assert not list((root / "releases").iterdir())


def test_unsupported_deploy_target_fails(recorded_run):
    result = runner.invoke(app, ["deploy", "--target", "gguf"])
    assert result.exit_code == 1
    assert "Unsupported deployment target" in result.output


@pytest.mark.parametrize(
    "metadata",
    [
        "{broken",
        '{"peft_type":"OTHER","r":16}',
        '{"peft_type":"LORA","r":true}',
        '{"peft_type":"LORA","r":0}',
    ],
)
def test_invalid_adapter_metadata_is_rejected(recorded_run, metadata):
    root, directory, run, _ = recorded_run
    (directory / "adapter/adapter_config.json").write_text(metadata)
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "Export error" in result.output
    assert not list((root / "releases").iterdir())


def test_database_and_snapshot_model_must_agree(recorded_run):
    root, _, run, _ = recorded_run
    conn = db.get_connection(root)
    conn.execute("UPDATE runs SET model_name = 'wrong-model' WHERE id = ?", (run,))
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "identity conflicts" in result.output


@pytest.fixture
def evaluated_run(recorded_run, monkeypatch):
    from moro.eval import runner as evaluation

    root, directory, run, config = recorded_run
    suite_path = root / "eval/support-golden-v1.yaml"
    suite_path.write_text(
        yaml.safe_dump(
            {
                "name": "support-golden-v1",
                "cases": [
                    {
                        "id": "one",
                        "messages": [{"role": "user", "content": "first"}],
                        "expect": {"contains": ["ok"]},
                        "tags": ["safety"],
                    },
                    {
                        "id": "two",
                        "messages": [{"role": "user", "content": "second"}],
                        "expect": {"contains": ["ok"]},
                    },
                ],
            }
        )
    )
    project_file = root / "moro.yaml"
    document = yaml.safe_load(project_file.read_text())
    document["release"]["require"] = {
        "eval_suite": "support-golden-v1",
        "min_pass_rate": 0.5,
        "safety_pass": True,
    }
    project_file.write_text(yaml.safe_dump(document))
    # Exercise production orchestration with a deterministic fake inference backend.
    monkeypatch.setattr(evaluation, "_load_generator", lambda *args, **kwargs: object())
    monkeypatch.setattr(evaluation, "_generate_response", lambda *args, **kwargs: "ok")
    result = runner.invoke(app, ["eval", "run", str(suite_path), "--run-id", run, "--json"])
    assert result.exit_code == 0, result.output
    evaluation_id = json.loads(result.output)["id"]
    return root, directory, run, evaluation_id


@pytest.mark.parametrize("command", [["export"], ["export", "--format", "ollama"], ["deploy"]])
def test_matching_evaluation_permits_release(evaluated_run, command):
    root, _, run, evaluation_id = evaluated_run
    result = runner.invoke(app, [*command, "--run-id", run])
    assert result.exit_code == 0, result.output
    if command == ["export"]:
        report = json.loads((root / "releases" / run / "manifest.json").read_text())["release_gate"]
    else:
        report = json.loads(next((root / "releases").rglob("release_gate.json")).read_text())
    assert report["status"] == "passed"
    assert report["evaluations"][0]["eval_id"] == evaluation_id


def test_displayed_eval_id_retrieves_report(evaluated_run):
    *_, evaluation_id = evaluated_run
    result = runner.invoke(app, ["eval", "report", evaluation_id, "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["id"] == evaluation_id


@pytest.mark.parametrize(
    "damage",
    [
        "adapter",
        "suite",
        "missing",
        "stub",
        "legacy",
        "partial",
        "unscored",
        "threshold",
        "safety",
        "id",
    ],
)
@pytest.mark.parametrize("command", ["export", "deploy"])
def test_release_blocks_insufficient_evidence(evaluated_run, damage, command):
    root, directory, run, evaluation_id = evaluated_run
    if damage == "adapter":
        (directory / "adapter/adapter_model.safetensors").write_bytes(b"replacement")
    elif damage == "suite":
        suite = root / "eval/support-golden-v1.yaml"
        suite.write_text(suite.read_text() + "\n# changed\n")
    else:
        conn = db.get_connection(root)
        row = conn.execute(
            "SELECT result_json FROM eval_runs WHERE id = ?", (evaluation_id,)
        ).fetchone()
        payload = json.loads(row[0])
        if damage == "missing":
            conn.execute("DELETE FROM eval_runs")
        else:
            if damage in ("stub", "legacy"):
                payload["execution_kind"] = damage
            elif damage == "partial":
                payload["cases"] = payload["cases"][:1]
            elif damage == "unscored":
                payload["fully_scored"] = False
            elif damage in ("threshold", "safety"):
                payload["cases"][0]["passed"] = False
                if damage == "threshold":
                    payload["cases"][1]["passed"] = False
                payload["pass_rate"] = 0 if damage == "threshold" else 0.5
            else:
                payload["id"] = "wrong"
            conn.execute(
                "UPDATE eval_runs SET result_json = ? WHERE id = ?",
                (json.dumps(payload), evaluation_id),
            )
        conn.commit()
        conn.close()
    result = runner.invoke(app, [command, "--run-id", run])
    assert result.exit_code == 1, result.output
    assert "Release blocked" in result.output
    assert not list((root / "releases").iterdir())


@pytest.mark.parametrize("field", ["min_improvement", "max_regression"])
def test_comparison_requirements_fail_closed(evaluated_run, field):
    root, _, run, _ = evaluated_run
    path = root / "moro.yaml"
    config = yaml.safe_load(path.read_text())
    config["release"]["require"][field] = 0.1
    path.write_text(yaml.safe_dump(config))
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "baseline comparison" in " ".join(result.output.split())


def test_saved_safety_policy_cannot_be_weakened(recorded_run):
    root, directory, run, config = recorded_run
    config.release.require.safety_pass = True
    (directory / "config.json").write_text(config.model_dump_json(indent=2))
    conn = db.get_connection(root)
    conn.execute(
        "UPDATE runs SET config_hash = ? WHERE id = ?", (sha256_text(config.model_dump_json()), run)
    )
    conn.commit()
    conn.close()
    # Current policy has safety_pass:false, but the saved policy still applies.
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "no evaluation" in result.output


def test_default_safety_policy_requires_tagged_cases(evaluated_run, monkeypatch):
    root, _, run, _ = evaluated_run
    path = root / "eval/support-golden-v1.yaml"
    suite = yaml.safe_load(path.read_text())
    suite["cases"][0]["tags"] = []
    path.write_text(yaml.safe_dump(suite))
    result = runner.invoke(app, ["eval", "run", str(path), "--run-id", run])
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 1
    assert "tagged 'safety'" in " ".join(result.output.split())


def test_old_snapshot_hash_survives_new_policy_default(recorded_run):
    root, directory, run, _ = recorded_run
    path = directory / "config.json"
    payload = json.loads(path.read_text())
    payload["release"]["require"].pop("min_pass_rate")
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(json.dumps(payload, indent=2))
    conn = db.get_connection(root)
    conn.execute("UPDATE runs SET config_hash = ? WHERE id = ?", (sha256_text(canonical), run))
    conn.commit()
    conn.close()
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    "policy", [{"min_pass_rate": 1.1}, {"min_pass_rate": -0.1}, {"min_pas_rate": 0.5}]
)
def test_invalid_release_policy_is_rejected(recorded_run, policy):
    root, _, run, _ = recorded_run
    path = root / "moro.yaml"
    config = yaml.safe_load(path.read_text())
    config["release"]["require"] = policy
    path.write_text(yaml.safe_dump(config))
    result = runner.invoke(app, ["export", "--run-id", run])
    assert result.exit_code != 0
    assert not list((root / "releases").iterdir())


def test_adapter_modification_during_eval_saves_no_result(recorded_run, monkeypatch):
    from moro.eval import runner as evaluation

    root, directory, run, _ = recorded_run
    monkeypatch.setattr(evaluation, "_load_generator", lambda *args, **kwargs: object())

    def generate(*args, **kwargs):
        (directory / "adapter/adapter_model.safetensors").write_bytes(b"modified")
        return "ok"

    monkeypatch.setattr(evaluation, "_generate_response", generate)
    result = runner.invoke(
        app, ["eval", "run", str(root / "eval/support-golden-v1.yaml"), "--run-id", run]
    )
    assert result.exit_code == 1
    assert "changed during execution" in result.output
    conn = db.get_connection(root)
    assert conn.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0] == 0
    conn.close()


def test_explicit_stub_execution_is_marked(recorded_run):
    from moro.eval.runner import run_suite

    root, directory, run, _ = recorded_run
    result = run_suite(
        root / "eval/support-golden-v1.yaml",
        str(directory / "adapter"),
        run_id=run,
        stub_responses={},
    )
    assert result.execution_kind == "stub"
    assert result.adapter_sha256


def test_missing_schema_dependency_is_not_a_model_failure(recorded_run, monkeypatch):
    import sys

    from moro.eval import runner as evaluation

    root, _, run, _ = recorded_run
    path = root / "eval/schema.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "schema",
                "cases": [
                    {
                        "id": "x",
                        "messages": [{"role": "user", "content": "q"}],
                        "expect": {"json_schema": {"type": "object"}},
                    }
                ],
            }
        )
    )
    monkeypatch.setitem(sys.modules, "jsonschema", None)

    def unexpected(*args, **kwargs):
        pytest.fail("missing scorer dependency must fail before generation")

    monkeypatch.setattr(evaluation, "_load_generator", unexpected)
    result = runner.invoke(app, ["eval", "run", str(path), "--run-id", run])
    assert result.exit_code == 1
    assert "scoring requires" in result.output


def test_eval_rejects_ambiguous_model_before_generation(recorded_run, monkeypatch):
    from moro.eval import runner as evaluation

    root, _, run, _ = recorded_run

    def unexpected(*args, **kwargs):
        pytest.fail("ambiguous evaluation must not load a model")

    monkeypatch.setattr(evaluation, "_load_generator", unexpected)
    result = runner.invoke(
        app,
        [
            "eval",
            "run",
            str(root / "eval/support-golden-v1.yaml"),
            "--run-id",
            run,
            "--base-model",
            "other",
        ],
    )
    assert result.exit_code == 1
    assert "not both" in result.output


@pytest.mark.parametrize("expect", [{"containz": ["ok"]}, {}, {"contains": [""]}, {"regex": ["["]}])
def test_invalid_checks_fail_before_model_loading(recorded_run, monkeypatch, expect):
    from moro.eval import runner as evaluation

    root, _, run, _ = recorded_run
    path = root / "eval/invalid.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "bad",
                "cases": [
                    {"id": "x", "messages": [{"role": "user", "content": "q"}], "expect": expect}
                ],
            }
        )
    )

    def unexpected(*args, **kwargs):
        pytest.fail("invalid suite must not load a model")

    monkeypatch.setattr(evaluation, "_load_generator", unexpected)
    result = runner.invoke(app, ["eval", "run", str(path), "--run-id", run])
    assert result.exit_code == 1
    conn = db.get_connection(root)
    assert conn.execute("SELECT COUNT(*) FROM eval_runs").fetchone()[0] == 0
    conn.close()
