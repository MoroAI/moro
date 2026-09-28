"""
Comprehensive Integration Tests for the MoroAI Interactive Mission Control Dashboard.

Covers:
- Dataset upload, listing, preview, compilation, and deletion
- Training initiation, stop/cancellation, and step telemetry
- Model registry queries, promotion, archiving, and comparison
- Deployment to Ollama/vLLM and interactive prompt testing
- System health, config management, and terminal execution
- Evaluation suites and DPO flywheel control
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moro.dashboard.mission_control import mission_app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a TestClient with project_root redirected to tmp_path."""
    # Ensure standard directory structure
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "compiled").mkdir(parents=True)
    (tmp_path / "data" / "dpo").mkdir(parents=True)
    (tmp_path / "runs").mkdir(parents=True)
    (tmp_path / "releases").mkdir(parents=True)
    (tmp_path / "eval").mkdir(parents=True)
    (tmp_path / ".moro").mkdir(parents=True)

    # Sample moro.yaml
    (tmp_path / "moro.yaml").write_text("""project:
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
""")

    # Sample raw data
    sample_file = tmp_path / "data" / "raw" / "test.jsonl"
    with open(sample_file, "w", encoding="utf-8") as f:
        f.write('{"prompt": "Hello", "completion": "Hi"}\n')
        f.write('{"prompt": "What is 2+2?", "completion": "4"}\n')

    monkeypatch.setattr("moro.dashboard.mission_control.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.utils.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.datasets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.training.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.models.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.deployment.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.system.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.evaluation.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.flywheel.get_project_root", lambda: tmp_path)

    return TestClient(mission_app)


class TestDashboardHtmlAndHealth:
    """Test dashboard serving and base health."""

    def test_serve_dashboard_html(self, client: TestClient):
        response = client.get("/")
        assert response.status_code == 200
        assert "MoroAI Mission Control" in response.text
        assert "dropzone" in response.text.lower()
        assert "Datasets" in response.text

    def test_dashboard_alias(self, client: TestClient):
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "MoroAI" in response.text

    def test_health_check(self, client: TestClient):
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data


class TestDatasetsApi:
    """Test datasets management API endpoints."""

    def test_list_datasets(self, client: TestClient):
        response = client.get("/api/datasets/")
        assert response.status_code == 200
        datasets = response.json()
        assert isinstance(datasets, list)
        assert len(datasets) >= 1
        assert any(d["name"] == "test.jsonl" for d in datasets)

    def test_upload_dataset(self, client: TestClient):
        file_content = b'{"messages": [{"role": "user", "content": "Howdy"}]}\n'
        response = client.post(
            "/api/datasets/upload",
            files={"file": ("uploaded_test.jsonl", io.BytesIO(file_content), "application/jsonl")},
            data={"name": "custom_name.jsonl", "auto_compile": "false"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "custom_name.jsonl"
        assert data["size_bytes"] == len(file_content)

    def test_preview_dataset(self, client: TestClient):
        response = client.get("/api/datasets/ds_test/preview")
        assert response.status_code == 200
        data = response.json()
        assert data["row_count"] == 2
        assert "prompt" in data["columns"]
        assert len(data["sample_rows"]) == 2

    def test_compile_dataset(self, client: TestClient):
        response = client.post("/api/datasets/ds_test/compile")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "compiling"

    def test_delete_dataset(self, client: TestClient, tmp_path: Path):
        # Create disposable dataset
        to_delete = tmp_path / "data" / "raw" / "to_delete.jsonl"
        to_delete.write_text('{"a": 1}\n')

        response = client.delete("/api/datasets/ds_to_delete")
        assert response.status_code == 200
        assert not to_delete.exists()


class TestTrainingApi:
    """Test training control and monitoring API endpoints."""

    def test_gpu_status(self, client: TestClient):
        response = client.get("/api/training/gpu/status")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data

    def test_start_and_monitor_training(self, client: TestClient):
        response = client.post(
            "/api/training/start",
            json={
                "model_name": "Qwen/Qwen2.5-1.5B-Instruct",
                "dataset_id": "test",
                "learning_rate": 0.0002,
                "batch_size": 1,
                "epochs": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        run_id = data["run_id"]
        assert data["status"] == "started"

        # Check run in list
        runs_resp = client.get("/api/training/runs")
        assert runs_resp.status_code == 200
        runs = runs_resp.json()
        assert any(r["run_id"] == run_id for r in runs)

        # Check metrics
        metrics_resp = client.get(f"/api/training/runs/{run_id}/metrics")
        assert metrics_resp.status_code == 200
        metrics = metrics_resp.json()
        assert "current_step" in metrics

        # Stop training
        stop_resp = client.post(f"/api/training/runs/{run_id}/stop")
        assert stop_resp.status_code == 200
        assert stop_resp.json()["status"] == "cancelled"


class TestModelsApi:
    """Test model registry, comparison, and promotion API endpoints."""

    def test_list_models(self, client: TestClient):
        response = client.get("/api/models/")
        assert response.status_code == 200
        models = response.json()
        assert len(models) >= 1

    def test_promote_and_compare_models(self, client: TestClient):
        models = client.get("/api/models/").json()
        model_id = models[0]["model_id"]

        # Promote
        promote_resp = client.post(f"/api/models/{model_id}/promote")
        assert promote_resp.status_code == 200
        assert promote_resp.json()["is_production"] is True

        # Compare model with itself or another
        comp_resp = client.get(f"/api/models/compare/{model_id}/{model_id}")
        assert comp_resp.status_code == 200
        comp_data = comp_resp.json()
        assert "winner" in comp_data
        assert comp_data["winner"] == model_id


class TestDeploymentApi:
    """Test deployment, Ollama check, and prompt testing endpoints."""

    def test_deployment_status(self, client: TestClient):
        response = client.get("/api/deployment/status")
        assert response.status_code == 200
        data = response.json()
        assert "ollama" in data

    def test_deploy_and_test_prompt(self, client: TestClient):
        # Deploy
        deploy_resp = client.post(
            "/api/deployment/deploy",
            json={"model_id": "test_model_v1", "target": "ollama"},
        )
        assert deploy_resp.status_code == 200
        dep = deploy_resp.json()
        assert dep["status"] == "running"

        # Test prompt
        test_resp = client.post(
            "/api/deployment/ollama/test",
            params={"model_name": "test_model_v1", "prompt": "What is MoroAI?"},
        )
        assert test_resp.status_code == 200
        test_data = test_resp.json()
        assert "response" in test_data
        assert "latency_ms" in test_data

        # Undeploy
        undep_resp = client.post(f"/api/deployment/undeploy/{dep['deployment_id']}")
        assert undep_resp.status_code == 200


class TestSystemApi:
    """Test system metrics, terminal execution, and configuration API endpoints."""

    def test_system_health(self, client: TestClient):
        response = client.get("/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "resources" in data

    def test_get_and_update_config(self, client: TestClient):
        get_resp = client.get("/api/system/config")
        assert get_resp.status_code == 200
        cfg = get_resp.json()
        assert "project" in cfg

        # Update config
        cfg["project"]["seed"] = 1234
        put_resp = client.put("/api/system/config", json=cfg)
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "updated"

    def test_terminal_execution_allowed(self, client: TestClient):
        response = client.post(
            "/api/system/terminal/execute",
            json={"command": "moro version"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "moro" in data["stdout"] or data["return_code"] == 0

    def test_terminal_execution_disallowed(self, client: TestClient):
        response = client.post(
            "/api/system/terminal/execute",
            json={"command": "rm -rf /"},
        )
        assert response.status_code == 400


class TestEvaluationAndFlywheelApi:
    """Test evaluation suites and continuous learning DPO endpoints."""

    def test_evaluation_workflow(self, client: TestClient):
        suites_resp = client.get("/api/evaluation/suites")
        assert suites_resp.status_code == 200

        run_resp = client.post(
            "/api/evaluation/run",
            json={"run_id": "test_eval_run", "suite_path": "eval/test.yaml"},
        )
        assert run_resp.status_code == 200
        assert run_resp.json()["status"] == "completed"

        results_resp = client.get("/api/evaluation/results/test_eval_run")
        assert results_resp.status_code == 200
        assert "pass_rate" in results_resp.json()

    def test_flywheel_workflow(self, client: TestClient):
        status_resp = client.get("/api/flywheel/status")
        assert status_resp.status_code == 200

        cycle_resp = client.post("/api/flywheel/cycle")
        assert cycle_resp.status_code == 200
        assert cycle_resp.json()["status"] in ["completed", "skipped"]

        pairs_resp = client.get("/api/flywheel/pairs")
        assert pairs_resp.status_code == 200
        assert "pairs" in pairs_resp.json()
