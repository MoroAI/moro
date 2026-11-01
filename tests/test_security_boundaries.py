"""Regression tests for the audit's concrete trust-boundary failures."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from moro.dashboard.mission_control import app

TOKEN = "audit-regression-" + "a" * 32


@pytest.fixture
def secured(tmp_path, monkeypatch):
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    for module in ["mission_control", "utils", "security", "api.datasets", "api.system"]:
        monkeypatch.setattr(f"moro.dashboard.{module}.get_project_root", lambda: tmp_path)
    return TestClient(app, base_url="http://127.0.0.1"), tmp_path


def test_http_authentication_and_both_terminal_routes(secured, monkeypatch):
    client, _ = secured

    def must_not_execute(*args, **kwargs):
        raise AssertionError("A web terminal started a process")

    monkeypatch.setattr("subprocess.run", must_not_execute)
    for route in ["/api/terminal/execute", "/api/system/terminal/execute"]:
        for payload in ["moro --help; printf marker", "python3 -c print(123)"]:
            assert client.post(route, json={"command": payload}).status_code == 401
            assert (
                client.post(
                    route, json={"command": payload}, headers={"Authorization": f"Bearer {TOKEN}"}
                ).status_code
                == 404
            )


def test_host_origin_and_websocket(secured):
    client, _ = secured
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/api/datasets/", headers={**auth, "Host": "evil.invalid"}).status_code == 403
    assert (
        client.get("/api/datasets/", headers={**auth, "Origin": "https://evil.invalid"}).status_code
        == 403
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/logs/stream"):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws/logs/stream", headers={**auth, "Origin": "https://evil.invalid"}
        ):
            pass


def test_session_login_csrf_and_expiry(secured):
    from moro.dashboard.security import session_value

    client, _ = secured
    assert client.post("/login", data={"token": "wrong"}).status_code == 401
    response = client.post("/login", data={"token": TOKEN}, follow_redirects=False)
    assert response.status_code == 303
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/datasets/").status_code == 200
    assert client.post("/api/terminal/execute", json={"command": "moro status"}).status_code == 403
    assert (
        client.post(
            "/api/terminal/execute",
            json={"command": "moro status"},
            headers={"Origin": "http://127.0.0.1"},
        ).status_code
        == 404
    )
    client.cookies.clear()
    client.cookies.set("moro_session", session_value(TOKEN, 1))
    assert client.get("/api/datasets/").status_code == 401


@pytest.mark.parametrize(
    "name", ["../../escape.txt", "/tmp/escape.txt", "sub\\escape.txt", "different.exe"]
)
def test_upload_names_cannot_escape(secured, name):
    client, root = secured
    response = client.post(
        "/api/datasets/upload",
        headers={"Authorization": f"Bearer {TOKEN}"},
        data={"name": name},
        files={"file": ("allowed.txt", b"audit marker")},
    )
    assert response.status_code == 400
    assert not list(root.rglob("*.txt"))


def test_upload_never_overwrites_or_follows_links(secured):
    client, root = secured
    raw = root / "data/raw"
    raw.mkdir(parents=True)
    outside = root / "outside.txt"
    outside.write_text("original")
    (raw / "linked.txt").symlink_to(outside)
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert client.get("/api/datasets/ds_linked/preview").status_code == 404
    response = client.post("/api/datasets/upload", files={"file": ("linked.txt", b"new")})
    assert response.status_code == 200
    assert outside.read_text() == "original"
    path = Path(response.json()["path"])
    assert path.read_text() == "new" and path.name != "linked.txt"
    assert path.stat().st_mode & 0o077 == 0


def test_upload_limits_and_invalid_content(secured):
    client, root = secured
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert (
        client.post("/api/datasets/upload", files={"file": ("bad.jsonl", b"not json")}).status_code
        == 400
    )
    assert not list((root / "data/raw").iterdir())
    assert (
        client.post(
            "/api/datasets/upload",
            files={"file": ("large.txt", io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)))},
        ).status_code
        == 413
    )
    assert not list((root / "data/raw").iterdir())


def test_analytics_rejects_expressions(secured):
    client, _ = secured
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    assert (
        client.get(
            "/api/analytics/viz/hyperparameter-heatmap",
            params={"x_param": "learning_rate || (SELECT 1)"},
        ).status_code
        == 400
    )


def test_json_schema_does_not_retrieve_remote_refs(monkeypatch):
    pytest.importorskip("jsonschema")
    import socket

    from moro.eval.models import EvalCase
    from moro.eval.scorers import score_case

    def deny(*args, **kwargs):
        raise AssertionError("Network must not be used")

    monkeypatch.setattr(socket.socket, "connect", deny)
    case = EvalCase.model_validate(
        {
            "id": "remote",
            "messages": [{"role": "user", "content": "x"}],
            "expect": {"json_schema": {"$ref": "http://127.0.0.1:9/private"}},
        }
    )
    from referencing.exceptions import Unresolvable

    with pytest.raises(Unresolvable):
        score_case(case, "{}")
    local = case.model_copy(
        update={
            "expect": case.expect.model_copy(
                update={
                    "json_schema": {
                        "$defs": {"object": {"type": "object"}},
                        "$ref": "#/$defs/object",
                    }
                }
            )
        }
    )
    assert score_case(local, "{}").passed


def test_complete_private_key_redaction():
    from moro.data.privacy import redact_text

    for text in [
        "-----BEGIN PRIVATE KEY-----\nSECRET_BODY\n-----END PRIVATE KEY-----",
        "-----BEGIN RSA PRIVATE KEY-----\nSECRET_BODY",
    ]:
        result, flags = redact_text(text)
        assert "SECRET_BODY" not in result and "private_key" in flags


def test_gguf_rejects_executable_project_name(tmp_path):
    from moro.core.errors import ExportError
    from moro.export.gguf import write_gguf_script

    with pytest.raises(ExportError):
        write_gguf_script(tmp_path, tmp_path / "out", project_name="$(touch marker)")


def test_invalid_or_stale_configuration_preserves_previous_file(secured):
    from moro.templates.project import default_moro_yaml

    client, root = secured
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    config = root / "moro.yaml"
    config.write_text(default_moro_yaml("config-test"))
    original = config.read_bytes()
    response = client.get("/api/system/config")
    value = response.json()
    tag = response.headers["etag"]
    value["training"]["batch_size"] = -99
    assert (
        client.put("/api/system/config", json=value, headers={"If-Match": tag}).status_code == 422
    )
    assert config.read_bytes() == original
    value["training"]["batch_size"] = 2
    assert client.put("/api/system/config", json=value).status_code == 428
    assert (
        client.put("/api/system/config", json=value, headers={"If-Match": tag}).status_code == 200
    )
    new_content = config.read_bytes()
    assert (
        client.put("/api/system/config", json=value, headers={"If-Match": tag}).status_code == 412
    )
    assert config.read_bytes() == new_content


def test_webhook_requires_auth_validates_and_deduplicates(tmp_path):
    from moro.flywheel.storage.schema import get_db_stats
    from moro.flywheel.webhook.receiver import WebhookConfig, set_config, webhook_app

    set_config(WebhookConfig(db_path=tmp_path / "feedback.db", api_key=TOKEN, batch_size=2))
    client = TestClient(webhook_app)
    payload = {
        "session_id": "one",
        "prompt": "question",
        "completion": "answer",
        "human_correction": "correction",
    }
    assert client.post("/webhook/ingest", json=payload).status_code == 403
    client.headers["X-API-Key"] = TOKEN
    assert client.post("/webhook/ingest", json=payload).status_code == 400
    client.headers["Idempotency-Key"] = "stable-test-request-12345"
    first = client.post("/webhook/ingest", json=payload)
    assert first.status_code == 200
    assert client.post("/webhook/ingest", json=payload).json() == first.json()
    assert get_db_stats(tmp_path / "feedback.db")["total_logs"] == 1
    assert (
        client.post("/webhook/ingest", json={**payload, "prompt": "different"}).status_code == 409
    )
    assert client.post("/webhook/ingest-batch", json={"logs": [payload] * 3}).status_code == 422
    assert client.post("/webhook/ingest", json={**payload, "user_rating": 99}).status_code == 422
    assert get_db_stats(tmp_path / "feedback.db")["total_logs"] == 1


def test_hook_scans_index_bytes_not_worktree(tmp_path):
    import os
    import subprocess
    import sys

    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    path = tmp_path / "customer_fixture.txt"
    path.write_text('key = "sk-' + "a" * 40 + '"')
    subprocess.run(["git", "add", "customer_fixture.txt"], cwd=tmp_path, check=True)
    path.write_text("sanitized but not staged")
    result = subprocess.run(
        [sys.executable, "-m", "moro.security.hook"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode == 1
    assert "customer_fixture.txt" in result.stdout
    assert "sk-" + "a" * 40 not in result.stdout


def test_gateway_preserves_conversation_and_measured_usage(secured, monkeypatch):
    import moro.dashboard.gateway as module

    requests = []

    async def upstream(method, path, payload=None):
        requests.append((method, path, payload))
        return {
            "message": {"content": "actual model output"},
            "prompt_eval_count": 17,
            "eval_count": 3,
        }

    monkeypatch.setattr(module, "ollama_request", upstream)
    client = TestClient(
        module.gateway_app,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    messages = [
        {"role": "system", "content": "Instructions"},
        {"role": "user", "content": "Question"},
    ]
    response = client.post(
        "/v1/chat/completions",
        json={"model": "local", "messages": messages, "max_tokens": 12, "temperature": 0.2},
    )
    assert response.status_code == 200
    assert response.json()["usage"]["total_tokens"] == 20
    assert requests[0][2]["messages"] == messages
    assert requests[0][2]["options"] == {"temperature": 0.2, "num_predict": 12}
    response = client.post(
        "/v1/chat/completions", json={"model": "local", "messages": messages, "stream": True}
    )
    assert response.status_code == 422


def test_gateway_never_invents_response_on_upstream_failure(secured, monkeypatch):
    import httpx

    import moro.dashboard.gateway as module

    async def unavailable(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx.AsyncClient, "request", unavailable)
    client = TestClient(
        module.gateway_app,
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert client.get("/v1/models").status_code == 503
    response = client.post(
        "/v1/chat/completions",
        json={"model": "missing", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 503
    assert "choices" not in response.json()


def test_training_lock_prevents_concurrent_execution_and_releases(tmp_path):
    from moro.core.errors import TrainingError
    from moro.training.locking import training_lock

    with training_lock(tmp_path):
        with pytest.raises(TrainingError, match="Another training"):
            with training_lock(tmp_path):
                pytest.fail("Concurrent training acquired the lock")
    with training_lock(tmp_path):
        pass
