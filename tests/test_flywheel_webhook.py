"""
Tests for the MoroAI Flywheel Webhook Receiver.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from moro.flywheel.webhook.receiver import (
    WebhookConfig,
    WebhookRequestHandler,
    set_config,
)


def run_test_server(db_path: Path, api_key: str | None = None):
    config = WebhookConfig(db_path=db_path, api_key=api_key)
    set_config(config)
    server = HTTPServer(("127.0.0.1", 0), WebhookRequestHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def test_webhook_health_and_ingest(tmp_path):
    db_file = tmp_path / "prod.db"
    server, port = run_test_server(db_file)
    base_url = f"http://127.0.0.1:{port}"

    try:
        # 1. Health check
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "healthy"
            assert data["pending_logs"] == 0

        # 2. Ingest single log
        single_payload = {
            "session_id": "sess-100",
            "prompt": "What is the capital of France?",
            "completion": "Paris is the capital of France.",
            "user_rating": 1.0,
            "metadata": {"model_name": "test-model"},
        }
        body = json.dumps(single_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/webhook/ingest",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "success"
            assert data["count"] == 1

        # 3. Ingest batch logs
        batch_payload = {
            "logs": [
                {
                    "session_id": "sess-101",
                    "prompt": "P1",
                    "completion": "Bad",
                    "human_correction": "Good",
                },
                {
                    "session_id": "sess-102",
                    "prompt": "P2",
                    "completion": "Awesome",
                    "user_rating": 1.0,
                },
            ]
        }
        body = json.dumps(batch_payload).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/webhook/ingest-batch",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "success"
            assert data["count"] == 2

        # 4. Check stats
        req = urllib.request.Request(f"{base_url}/webhook/stats")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            stats = json.loads(resp.read().decode())
            assert stats["total_logs"] == 3
            assert stats["pending_logs"] == 3

    finally:
        server.shutdown()
        server.server_close()


def test_webhook_authentication(tmp_path):
    db_file = tmp_path / "prod.db"
    server, port = run_test_server(db_file, api_key="secret-token-xyz")
    base_url = f"http://127.0.0.1:{port}"

    try:
        # /health is public
        req = urllib.request.Request(f"{base_url}/health")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

        # /webhook/stats without auth fails with 403
        req = urllib.request.Request(f"{base_url}/webhook/stats")
        try:
            urllib.request.urlopen(req)
            assert False, "Should have failed with 403"
        except urllib.error.HTTPError as exc:
            assert exc.code == 403

        # /webhook/stats with auth succeeds
        req = urllib.request.Request(
            f"{base_url}/webhook/stats",
            headers={"X-API-Key": "secret-token-xyz"},
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

    finally:
        server.shutdown()
        server.server_close()
