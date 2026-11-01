"""P0 operation API acceptance: actual services, strict inputs and no shell."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

TOKEN = "operation-test-token-" + "a" * 32


@pytest.fixture
def client(tmp_project, sample_jsonl, monkeypatch):
    from moro.config.loader import load_config
    from moro.dashboard.mission_control import mission_app

    monkeypatch.chdir(tmp_project)
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    cfg = load_config(tmp_project / "moro.yaml")
    cfg.dataset.min_quality_score = 0
    source = tmp_project / cfg.dataset.source
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(sample_jsonl.read_bytes())
    (tmp_project / "moro.yaml").write_text(cfg.model_dump_json())
    return TestClient(mission_app, base_url="http://127.0.0.1")


def call(client, operation, body):
    return client.post(
        f"/api/operations/{operation}", json=body, headers={"Authorization": f"Bearer {TOKEN}"}
    )


@pytest.mark.parametrize("path", ["/api/terminal/execute", "/api/system/terminal/execute"])
def test_removed_routes_not_registered_and_cannot_execute(client, monkeypatch, path):
    def forbidden(*args, **kwargs):
        pytest.fail("Web request attempted subprocess execution")

    monkeypatch.setattr("subprocess.run", forbidden)
    monkeypatch.setattr("subprocess.Popen", forbidden)
    assert path not in client.app.openapi()["paths"]
    result = client.post(
        path,
        json={"command": "python3 -c print(123); id"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert result.status_code == 404


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer incorrect"}])
def test_operations_require_auth(client, headers):
    assert client.post("/api/operations/list_datasets", json={}, headers=headers).status_code == 401


def test_auth_disable_variable_and_query_token_do_not_bypass_auth(client, monkeypatch):
    monkeypatch.setenv("MORO_AUTH_DISABLED", "1")
    assert client.post(f"/api/operations/list_datasets?token={TOKEN}", json={}).status_code == 401
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(f"ws://127.0.0.1/api/system/ws/health?token={TOKEN}"):
            pass
    assert error.value.code == 1008


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "evil.example"},
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:9999"},
    ],
)
def test_host_and_exact_origin_rejected(client, headers):
    result = client.post(
        "/api/operations/list_datasets",
        json={},
        headers={"Authorization": f"Bearer {TOKEN}", **headers},
    )
    assert result.status_code == 403


def test_unknown_operation_is_404(client):
    assert call(client, "shell_exec", {"command": "id"}).status_code == 404


@pytest.mark.parametrize(
    "operation,body",
    [
        ("list_datasets", {"command": "id"}),
        ("list_datasets", {"limit": True}),
        ("list_datasets", {"limit": "10"}),
        ("list_datasets", {"limit": 501}),
        ("list_datasets", {"offset": -1}),
        ("preview_dataset", {"dataset_id": "../../../etc/passwd"}),
        ("preview_dataset", {"dataset_id": "ds_support", "row_limit": 101}),
        ("start_training", {"dataset_id": "ds_missing", "command": "id"}),
        ("start_training", {"dataset_id": "ds_missing", "recipe_id": "unimplemented"}),
        ("compile_dataset", {"dataset_id": "ds_support", "dry_run": True}),
        ("get_job_status", {"job_id": "../../other"}),
        ("stop_job", {"job_id": "run;id"}),
        ("resume_job", {"job_id": "run;id"}),
    ],
)
def test_strict_input_rejected_without_dispatch(client, monkeypatch, operation, body):
    from moro.dashboard import operations

    def forbidden(*args, **kwargs):
        pytest.fail("Invalid request reached handler")

    schema, _ = operations.HANDLERS[operation]
    monkeypatch.setitem(operations.HANDLERS, operation, (schema, forbidden))
    result = call(client, operation, body)
    assert result.status_code == 422
    assert all("input" not in error for error in result.json()["detail"])


def test_real_compile_preview_and_pagination(client):
    result = call(client, "list_datasets", {"limit": 1})
    assert result.status_code == 200
    rows = result.json()["payload"]["datasets"]
    assert len(rows) == 1
    source_id = rows[0]["id"]
    compiled = call(client, "compile_dataset", {"dataset_id": source_id})
    assert compiled.status_code == 200, compiled.text
    version = compiled.json()["payload"]["version_id"]
    assert (Path.cwd() / "data/versions" / version / "manifest.json").exists()
    preview = call(client, "preview_dataset", {"dataset_id": version, "row_limit": 1})
    assert preview.status_code == 200
    assert len(preview.json()["payload"]["sample_rows"]) == 1
    assert "messages" in preview.json()["payload"]["sample_rows"][0]
    assert call(client, "list_datasets", {"offset": 100}).json()["payload"]["datasets"] == []


@pytest.mark.parametrize(
    "operation,body,expected",
    [
        ("preview_dataset", {"dataset_id": "missing"}, 404),
        ("compile_dataset", {"dataset_id": "missing"}, 404),
        ("start_training", {"dataset_id": "missing"}, 422),
        ("get_job_status", {"job_id": "missing"}, 404),
        ("stop_job", {"job_id": "missing"}, 404),
        ("resume_job", {"job_id": "missing"}, 404),
    ],
)
def test_missing_resources_never_report_success(client, operation, body, expected):
    response = call(client, operation, body)
    assert response.status_code == expected, response.text
    assert response.json().get("ok") is not True


def test_recorded_run_status_and_no_pretend_cancellation(client):
    from moro.storage import db

    conn = db.get_connection(Path.cwd())
    project = db.get_or_create_project(conn, "test-project", "local_only")
    run_id = db.create_run(conn, project, "config-hash", "local-model", "none", "runs/fixture")
    conn.close()
    status = call(client, "get_job_status", {"job_id": run_id})
    assert status.status_code == 200
    assert status.json()["payload"]["run_id"] == run_id
    assert call(client, "stop_job", {"job_id": run_id}).status_code == 409
    assert (
        call(client, "get_job_status", {"job_id": run_id}).json()["payload"]["status"]
        == status.json()["payload"]["status"]
    )


def test_browser_session_authenticates_operations_and_websocket(client, monkeypatch):
    from moro.dashboard.api import system

    async def health():
        return system.SystemHealth(
            status="test", timestamp="fixture", services={}, resources={}, active_runs=0
        )

    monkeypatch.setattr(system, "get_system_health", health)
    origin = {"Origin": "http://127.0.0.1"}
    assert (
        client.post(
            "/login", data={"token": TOKEN}, headers=origin, follow_redirects=False
        ).status_code
        == 303
    )
    assert client.post("/api/operations/list_datasets", json={}).status_code == 403
    assert client.post("/api/operations/list_datasets", json={}, headers=origin).status_code == 200
    with client.websocket_connect("ws://127.0.0.1/api/system/ws/health", headers=origin) as ws:
        assert ws.receive_json()["status"] == "test"


def test_dashboard_does_not_offer_shell_or_fabricated_command_success(client):
    html = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"}).text
    assert "/api/operations/" in html
    for removed in (
        "/api/terminal/",
        "triggerCommand(",
        "new Terminal(",
        "Command executed.",
        "sess-prod-001",
        "Run 1: Baseline LoRA",
        "98.4%",
        "100.0%",
        "128 tok/s",
        "4.2 GB",
        "All Nodes Operational",
        "qwen-quantum",
        "64GB RAM",
    ):
        assert removed not in html
    assert "response.ok" in html


def test_webhook_to_dashboard_feedback_uses_one_database(client, monkeypatch):
    from moro.dashboard.mission_control import FlywheelMonitor
    from moro.flywheel.webhook import receiver

    auth = {"Authorization": f"Bearer {TOKEN}"}
    status = client.get("/api/flywheel/status", headers=auth).json()
    assert status["total_pairs_generated"] == 0 and status["status"] == "idle"
    assert client.get("/api/flywheel/pairs", headers=auth).json() == {"pairs": [], "total": 0}
    db_path = Path.cwd() / "data/production_logs.db"
    monkeypatch.setattr(receiver, "_config", receiver.WebhookConfig(db_path, TOKEN))
    webhook = TestClient(receiver.webhook_app)
    payload = {
        "session_id": "fixture-session",
        "prompt": "How do I reset a password?",
        "completion": "Share it publicly.",
        "human_correction": "Use the account recovery form.",
    }
    response = webhook.post(
        "/webhook/ingest",
        json=payload,
        headers={"X-API-Key": TOKEN, "Idempotency-Key": "one-database-fixture"},
    )
    assert response.status_code == 200
    assert client.get("/api/flywheel/status", headers=auth).json()["pending_logs"] == 1
    cycle = client.post("/api/flywheel/cycle", headers=auth)
    assert cycle.status_code == 200
    assert cycle.json()["status"] == "extracted" and cycle.json()["pairs_generated"] == 1
    pairs = client.get("/api/flywheel/pairs", headers=auth).json()
    assert pairs["total"] == 1
    assert pairs["pairs"][0]["source_log_id"] == response.json()["log_ids"][0]
    assert pairs["pairs"][0]["chosen"] == payload["human_correction"]
    status = client.get("/api/flywheel/status", headers=auth).json()
    assert status["pending_logs"] == 0 and status["total_pairs_generated"] == 1
    assert FlywheelMonitor(Path.cwd()).get_status()["pairs_generated"] == 1
    assert not (Path.cwd() / ".moro/production.db").exists()
    assert client.post("/api/flywheel/cycle", headers=auth).json()["status"] == "skipped"
    assert client.get("/api/flywheel/pairs?limit=-1", headers=auth).status_code == 422
