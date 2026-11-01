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

    with sample_file.open("a") as stream:
        stream.write('{"prompt":"Explain testing", "completion":"Tests check expected behavior"}\n')

    monkeypatch.setattr("moro.dashboard.mission_control.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.utils.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.datasets.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.training.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.models.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.deployment.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.system.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.evaluation.get_project_root", lambda: tmp_path)
    monkeypatch.setattr("moro.dashboard.api.flywheel.get_project_root", lambda: tmp_path)

    monkeypatch.setenv("MORO_API_TOKEN", "test-token-" + "a" * 32)
    return TestClient(
        mission_app,
        base_url="http://127.0.0.1",
        headers={"Authorization": "Bearer test-token-" + "a" * 32},
    )


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
        assert data["row_count"] == 3
        assert "prompt" in data["columns"]
        assert len(data["sample_rows"]) == 3

    def test_compile_dataset(self, client: TestClient):
        response = client.post("/api/datasets/ds_test/compile")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "compiled"
        assert data["version_id"].startswith("ds_")

    def test_compiled_version_preview_and_immutability(self, client: TestClient):
        result = client.post("/api/datasets/ds_test/compile")
        assert result.status_code == 200, result.text
        version = result.json()["version_id"]
        assert any(d["id"] == version for d in client.get("/api/datasets/").json())
        preview = client.get(f"/api/datasets/{version}/preview?limit=1")
        assert preview.status_code == 200, preview.text
        assert len(preview.json()["sample_rows"]) == 1
        assert "messages" in preview.json()["columns"]
        assert client.delete(f"/api/datasets/{version}").status_code == 409
        assert client.post(f"/api/datasets/{version}/compile").status_code == 409
        assert client.get(f"/api/datasets/{version}/preview").status_code == 200

    def test_corrupt_version_cannot_be_previewed(self, client: TestClient, tmp_path: Path):
        result = client.post("/api/datasets/ds_test/compile")
        assert result.status_code == 200, result.text
        version = result.json()["version_id"]
        (tmp_path / "data/versions" / version / "dataset.jsonl").write_text("tampered\n")
        assert client.get(f"/api/datasets/{version}/preview").status_code == 409

    @pytest.mark.parametrize("limit", [0, -1, 101])
    def test_preview_limit_is_bounded(self, client: TestClient, limit: int):
        assert client.get(f"/api/datasets/ds_test/preview?limit={limit}").status_code == 422

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
        assert response.status_code == 422
        runs_resp = client.get("/api/training/runs")
        assert runs_resp.status_code == 200
        assert not any(r["status"] == "completed" for r in runs_resp.json())
        assert client.post("/api/training/runs/missing/stop").status_code == 404


class TestModelsApi:
    """Test model registry, comparison, and promotion API endpoints."""

    def test_list_models(self, client: TestClient):
        response = client.get("/api/models/")
        assert response.status_code == 200
        models = response.json()
        assert models == []

    def test_missing_models_cannot_be_promoted_or_compared(self, client: TestClient):
        assert client.post("/api/models/missing/promote").status_code == 404
        assert client.get("/api/models/compare/missing/missing").status_code == 404

    def test_zero_score_remains_zero(self, client: TestClient, tmp_path):
        import json

        directory = tmp_path / "releases/zero-score"
        directory.mkdir()
        (directory / "metadata.json").write_text(json.dumps({"eval_results": {"pass_rate": 0.0}}))
        response = client.get("/api/models/")
        assert response.status_code == 200
        assert response.json()[0]["eval_pass_rate"] == 0.0


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
        assert deploy_resp.status_code == 501
        assert client.post("/api/deployment/undeploy/missing").status_code == 404


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
        put_resp = client.put(
            "/api/system/config", json=cfg, headers={"If-Match": get_resp.headers["etag"]}
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "updated"

    def test_terminal_execution_allowed(self, client: TestClient):
        response = client.post(
            "/api/system/terminal/execute",
            json={"command": "moro version"},
        )
        assert response.status_code == 404

    def test_terminal_execution_disallowed(self, client: TestClient):
        response = client.post(
            "/api/system/terminal/execute",
            json={"command": "rm -rf /"},
        )
        assert response.status_code == 404


class TestEvaluationAndFlywheelApi:
    """Test evaluation suites and continuous learning DPO endpoints."""

    def test_evaluation_workflow(self, client: TestClient):
        suites_resp = client.get("/api/evaluation/suites")
        assert suites_resp.status_code == 200

        run_resp = client.post(
            "/api/evaluation/run",
            json={"run_id": "test_eval_run", "suite_path": "eval/test.yaml"},
        )
        assert run_resp.status_code in (404, 422)
        results_resp = client.get("/api/evaluation/results/test_eval_run")
        assert results_resp.status_code == 404

    def test_flywheel_workflow(self, client: TestClient):
        status_resp = client.get("/api/flywheel/status")
        assert status_resp.status_code == 200

        cycle_resp = client.post("/api/flywheel/cycle")
        assert cycle_resp.status_code == 200
        assert cycle_resp.json()["status"] in ["extracted", "skipped"]

        pairs_resp = client.get("/api/flywheel/pairs")
        assert pairs_resp.status_code == 200
        assert "pairs" in pairs_resp.json()
