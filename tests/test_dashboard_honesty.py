"""Frontend honesty regression tests: unmeasured metrics stay null.

Covers:
- Missing evaluation evidence yields null pass rate/delta (never 0.88/0.13).
- A measured 0.0 is preserved and distinct from unmeasured (None).
- Model comparison requires measured pass rates (409) and discloses its basis.
- The dashboard template surfaces stop_job, training hyperparameters, and
  not-measured states without referencing removed vendor assets.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moro.dashboard.mission_control import mission_app

TOKEN = "honesty-test-token-" + "a" * 32


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "compiled").mkdir(parents=True)
    (tmp_path / "releases").mkdir(parents=True)
    (tmp_path / "eval").mkdir(parents=True)
    (tmp_path / ".moro").mkdir(parents=True)
    (tmp_path / "moro.yaml").write_text(
        """project:
  name: test-project
  privacy_mode: local_only
  seed: 42
dataset:
  source: ./data/raw/test.jsonl
  format: jsonl
model:
  name: Qwen/Qwen2.5-1.5B-Instruct
  quantization: nf4
training:
  learning_rate: 0.0002
  batch_size: 1
  epochs: 1
"""
    )

    monkeypatch.setattr("moro.dashboard.mission_control.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.utils.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.datasets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.training.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.models.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.deployment.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.system.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.evaluation.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.flywheel.get_project_root", lambda: tmp_path)
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    return TestClient(
        mission_app,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )


def _release(tmp_path: Path, name: str, eval_results: dict | None) -> None:
    directory = tmp_path / "releases" / name
    directory.mkdir(parents=True)
    if eval_results is not None:
        (directory / "metadata.json").write_text(json.dumps({"eval_results": eval_results}))


def _by_id(models: list[dict], model_id: str) -> dict:
    return next(m for m in models if m["model_id"] == model_id)


class TestUnmeasuredMetricsAreNull:
    def test_missing_metadata_yields_null(self, client: TestClient, tmp_path: Path):
        (tmp_path / "releases" / "no-evidence").mkdir()
        models = client.get("/api/models/").json()
        model = _by_id(models, "mod_no-evidence")
        assert model["eval_pass_rate"] is None
        assert model["eval_delta"] is None

    def test_empty_eval_results_yield_null(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "empty-results", {})
        models = client.get("/api/models/").json()
        model = _by_id(models, "mod_empty-results")
        assert model["eval_pass_rate"] is None
        assert model["eval_delta"] is None

    def test_zero_pass_rate_is_measured_not_missing(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "zero-score", {"pass_rate": 0.0})
        models = client.get("/api/models/").json()
        model = _by_id(models, "mod_zero-score")
        assert model["eval_pass_rate"] == 0.0
        assert model["eval_pass_rate"] is not None
        assert model["eval_delta"] is None

    def test_measured_values_preserved(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "measured", {"pass_rate": 0.8, "eval_delta": 0.05})
        models = client.get("/api/models/").json()
        model = _by_id(models, "mod_measured")
        assert model["eval_pass_rate"] == 0.8
        assert model["eval_delta"] == 0.05

    def test_non_numeric_payload_is_unmeasured(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "bad-types", {"pass_rate": "high", "eval_delta": True})
        models = client.get("/api/models/").json()
        model = _by_id(models, "mod_bad-types")
        assert model["eval_pass_rate"] is None
        assert model["eval_delta"] is None


class TestCompareRequiresMeasured:
    def test_compare_rejects_unmeasured(self, client: TestClient, tmp_path: Path):
        (tmp_path / "releases" / "unmeasured").mkdir()
        _release(tmp_path, "scored", {"pass_rate": 0.5})
        assert client.get("/api/models/compare/mod_unmeasured/mod_scored").status_code == 409
        assert client.get("/api/models/compare/mod_unmeasured/mod_unmeasured").status_code == 409

    def test_compare_treats_zero_as_measured(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "zero-a", {"pass_rate": 0.0})
        _release(tmp_path, "half-b", {"pass_rate": 0.5})
        response = client.get("/api/models/compare/mod_zero-a/mod_half-b")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["winner"] == "mod_half-b"
        assert data["winner_basis"] == "eval_pass_rate"
        assert data["comparison"]["metrics"]["eval_delta"]["model_a"] is None

    def test_compare_uses_delta_only_when_both_measured(self, client: TestClient, tmp_path: Path):
        _release(tmp_path, "with-delta", {"pass_rate": 0.6, "eval_delta": 0.1})
        _release(tmp_path, "without-delta", {"pass_rate": 0.75})
        response = client.get("/api/models/compare/mod_with-delta/mod_without-delta")
        assert response.status_code == 200, response.text
        data = response.json()
        # Delta omitted (unmeasured for one side): 0.75 beats 0.6 on pass rate.
        assert data["winner"] == "mod_without-delta"
        assert data["winner_basis"] == "eval_pass_rate"


class TestStopJobHonesty:
    def test_stop_job_reports_409_for_recorded_run(self, client: TestClient, tmp_path: Path):
        from moro.storage import db

        conn = db.get_connection(tmp_path)
        project = db.get_or_create_project(conn, "test-project", "local_only")
        run_id = db.create_run(conn, project, "hash", "model", "none", "runs/fixture")
        conn.commit()
        conn.close()
        response = client.post("/api/operations/stop_job", json={"job_id": run_id})
        assert response.status_code == 409
        assert response.json().get("ok") is not True


class TestTemplateHonesty:
    def test_operations_surface_stop_job_and_hyperparams(self, client: TestClient):
        html = client.get("/").text
        assert 'value="stop_job"' in html
        assert "trainingParams" in html
        for field in (
            "learning_rate",
            "batch_size",
            "epochs",
            "lora_r",
            "lora_alpha",
            "max_seq_length",
            "gradient_checkpointing",
        ):
            assert field in html

    def test_template_shows_not_measured_and_no_invented_vendor(self, client: TestClient):
        html = client.get("/").text
        assert "not measured" in html
        assert "Evaluation delta" in html
        assert "xterm" not in html.lower()
        assert "Supabase" not in html
        assert "Pearson coefficients" not in html

    def test_panels_wired_to_real_endpoints(self, client: TestClient):
        html = client.get("/").text
        assert "promoteModel" in html
        assert "compareRegistryModels" in html
        assert "runEvaluation" in html
        assert "/api/evaluation/run" in html
        assert "fetchHeatmap" in html
        assert "/api/analytics/viz/hyperparameter-heatmap" in html
        assert "statusDot(systemStatus.database)" in html
