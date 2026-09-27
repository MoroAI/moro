"""
MoroAI Production Webhook Receiver.

An HTTP service that accepts inference logs from production chat UIs
and writes them directly into the SQLite production log database.

Works out of the box with Python standard library http.server (zero dependencies).
"""

from __future__ import annotations

import json
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from moro.flywheel.storage.schema import get_db_stats, get_production_db


class WebhookConfig:
    """Configuration for the webhook receiver."""

    def __init__(
        self,
        db_path: Path = Path("data/production_logs.db"),
        api_key: str | None = None,
        batch_size: int = 50,
    ):
        self.db_path = Path(db_path)
        self.api_key = api_key
        self.batch_size = batch_size


_config: WebhookConfig | None = None


def get_config() -> WebhookConfig:
    global _config
    if _config is None:
        _config = WebhookConfig()
    return _config


def set_config(config: WebhookConfig) -> None:
    global _config
    _config = config


class WebhookRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for receiving production inference logs."""

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _verify_auth(self) -> bool:
        config = get_config()
        if not config.api_key:
            return True
        key = self.headers.get("X-API-Key")
        return key == config.api_key

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        config = get_config()

        if parsed.path == "/health":
            db_exists = config.db_path.exists()
            pending = 0
            total = 0
            if db_exists:
                try:
                    stats = get_db_stats(config.db_path)
                    pending = stats["pending_logs"]
                    total = stats["total_logs"]
                except Exception:
                    pass
            self._send_json(200, {
                "status": "healthy",
                "database_path": str(config.db_path),
                "database_exists": db_exists,
                "pending_logs": pending,
                "total_logs": total,
            })
            return

        if not self._verify_auth():
            self._send_json(403, {"error": "Invalid or missing X-API-Key"})
            return

        if parsed.path == "/webhook/stats":
            stats = get_db_stats(config.db_path)
            self._send_json(200, {"status": "success", "database_path": str(config.db_path), **stats})
            return

        self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if not self._verify_auth():
            self._send_json(403, {"error": "Invalid or missing X-API-Key"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid JSON payload: {exc}"})
            return

        config = get_config()
        conn = get_production_db(config.db_path)

        if parsed.path == "/webhook/ingest":
            try:
                log_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO inference_logs (
                        log_id, session_id, model_name, prompt, completion,
                        context, user_rating, human_correction, latency_ms,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        log_id,
                        payload.get("session_id", "default"),
                        payload.get("metadata", {}).get("model_name", "production"),
                        payload.get("prompt", ""),
                        payload.get("completion", ""),
                        payload.get("context"),
                        payload.get("user_rating"),
                        payload.get("human_correction"),
                        payload.get("latency_ms"),
                        json.dumps(payload.get("metadata", {})),
                    ),
                )
                conn.commit()
                self._send_json(200, {
                    "status": "success",
                    "log_ids": [log_id],
                    "count": 1,
                    "message": "Log ingested successfully",
                })
            except Exception as exc:
                self._send_json(500, {"error": f"Failed to write log: {exc}"})
            finally:
                conn.close()
            return

        elif parsed.path == "/webhook/ingest-batch":
            logs = payload.get("logs", [])
            log_ids: list[str] = []
            try:
                cursor = conn.cursor()
                for item in logs:
                    lid = str(uuid.uuid4())
                    log_ids.append(lid)
                    cursor.execute(
                        """
                        INSERT INTO inference_logs (
                            log_id, session_id, model_name, prompt, completion,
                            context, user_rating, human_correction, latency_ms,
                            metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            lid,
                            item.get("session_id", "default"),
                            item.get("metadata", {}).get("model_name", "production"),
                            item.get("prompt", ""),
                            item.get("completion", ""),
                            item.get("context"),
                            item.get("user_rating"),
                            item.get("human_correction"),
                            item.get("latency_ms"),
                            json.dumps(item.get("metadata", {})),
                        ),
                    )
                conn.commit()
                self._send_json(200, {
                    "status": "success",
                    "log_ids": log_ids,
                    "count": len(log_ids),
                    "message": f"Successfully ingested {len(log_ids)} logs",
                })
            except Exception as exc:
                self._send_json(500, {"error": f"Failed to batch write logs: {exc}"})
            finally:
                conn.close()
            return

        self._send_json(404, {"error": "Endpoint not found"})


def start_webhook_receiver(
    host: str = "127.0.0.1",
    port: int = 8001,
    api_key: str | None = None,
    db_path: Path | None = None,
):
    """Start the webhook receiver HTTP server."""
    config = WebhookConfig(
        db_path=db_path or Path("data/production_logs.db"),
        api_key=api_key,
    )
    set_config(config)
    server_address = (host, port)
    httpd = HTTPServer(server_address, WebhookRequestHandler)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
