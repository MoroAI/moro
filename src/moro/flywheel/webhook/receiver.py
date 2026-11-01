"""Authenticated, bounded and idempotent production feedback ingestion."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from moro.dashboard.security import access_token
from moro.flywheel.models import InferenceLogPayload
from moro.flywheel.storage.schema import get_db_stats, get_production_db

MAX_BODY_BYTES = 1024 * 1024


class WebhookConfig:
    def __init__(
        self,
        db_path: Path = Path("data/production_logs.db"),
        api_key: str | None = None,
        batch_size: int = 50,
    ):
        self.db_path = Path(db_path)
        self.api_key = api_key or access_token()
        if len(self.api_key) < 32:
            raise ValueError("Webhook API key must contain at least 32 characters")
        if not 1 <= batch_size <= 1000:
            raise ValueError("Webhook batch size must be between 1 and 1000")
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


def authenticated(key: str) -> bool:
    return hmac.compare_digest(key.encode(), get_config().api_key.encode())


def ingest(payload: object, *, batch: bool, idempotency_key: str) -> dict:
    config = get_config()
    if not 16 <= len(idempotency_key) <= 128 or not idempotency_key.isascii():
        raise HTTPException(400, "A stable Idempotency-Key of 16–128 ASCII characters is required")
    if not isinstance(payload, dict):
        raise HTTPException(422, "Expected a JSON object")
    items = payload.get("logs") if batch else [payload]
    if not isinstance(items, list) or not 1 <= len(items) <= config.batch_size:
        raise HTTPException(422, "Invalid or excessive batch size")
    try:
        logs = [InferenceLogPayload.model_validate(item) for item in items]
    except ValidationError as exc:
        raise HTTPException(422, "Invalid feedback fields or rating") from exc
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    sender = hashlib.sha256(config.api_key.encode()).hexdigest()
    request_id = hashlib.sha256((sender + ":" + idempotency_key).encode()).hexdigest()
    conn = get_production_db(config.db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS webhook_requests (request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, result_json TEXT NOT NULL)"
        )
        conn.execute("BEGIN IMMEDIATE")
        previous = conn.execute(
            "SELECT digest, result_json FROM webhook_requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if previous:
            if previous["digest"] != digest:
                raise HTTPException(409, "Idempotency-Key was already used for different feedback")
            return json.loads(previous["result_json"])
        ids = []
        for log in logs:
            log_id = str(uuid.uuid4())
            ids.append(log_id)
            metadata = {**log.metadata, "sender_id": sender, "ingestion_request": request_id}
            metadata.pop("log_id", None)
            conn.execute(
                """INSERT INTO inference_logs
                (log_id,session_id,model_name,prompt,completion,context,user_rating,human_correction,latency_ms,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    log_id,
                    log.session_id,
                    str(metadata.get("model_name", "production")),
                    log.prompt,
                    log.completion,
                    log.context,
                    log.user_rating,
                    log.human_correction,
                    log.latency_ms,
                    json.dumps(metadata),
                ),
            )
        result = {"status": "success", "log_ids": ids, "count": len(ids)}
        conn.execute(
            "INSERT INTO webhook_requests VALUES (?,?,?)", (request_id, digest, json.dumps(result))
        )
        conn.commit()
        return result
    finally:
        conn.close()


class WebhookRequestHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _verify_auth(self) -> bool:
        # No browser-origin access to this machine-to-machine receiver.
        return not self.headers.get("Origin") and authenticated(self.headers.get("X-API-Key", ""))

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "healthy", "service": "moro-webhook"})
        elif not self._verify_auth():
            self._send_json(403, {"error": "Invalid or missing X-API-Key"})
        elif path == "/webhook/stats":
            self._send_json(200, {"status": "success", **get_db_stats(get_config().db_path)})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if not self._verify_auth():
            self._send_json(403, {"error": "Invalid or missing X-API-Key"})
            return
        path = urlsplit(self.path).path
        if path not in ("/webhook/ingest", "/webhook/ingest-batch"):
            self._send_json(404, {"error": "Not found"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_BODY_BYTES or self.headers.get("Transfer-Encoding"):
                raise HTTPException(413, "Invalid or excessive body length")
            body = self.rfile.read(size)
            if len(body) != size:
                raise HTTPException(400, "Incomplete request body")
            payload = json.loads(body)
            result = ingest(
                payload,
                batch=path.endswith("-batch"),
                idempotency_key=self.headers.get("Idempotency-Key", ""),
            )
            self._send_json(200, result)
        except HTTPException as exc:
            self._send_json(exc.status_code, {"error": exc.detail})
        except (TimeoutError, ValueError, UnicodeError):
            self._send_json(400, {"error": "Invalid or incomplete JSON body"})
        except Exception:
            self._send_json(500, {"error": "Feedback could not be persisted"})


webhook_app = FastAPI(title="MoroAI feedback receiver")


@webhook_app.get("/health")
def health():
    return {"status": "healthy", "service": "moro-webhook"}


@webhook_app.post("/webhook/ingest")
@webhook_app.post("/webhook/ingest-batch")
async def receive_feedback(request: Request):
    if request.headers.get("origin") or not authenticated(request.headers.get("x-api-key", "")):
        raise HTTPException(403, "Invalid or missing X-API-Key")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BODY_BYTES:
            raise HTTPException(413, "Request too large")
    try:
        payload = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(
        ingest,
        payload,
        batch=request.url.path.endswith("-batch"),
        idempotency_key=request.headers.get("idempotency-key", ""),
    )


@webhook_app.get("/webhook/stats")
def stats(request: Request):
    if request.headers.get("origin") or not authenticated(request.headers.get("x-api-key", "")):
        raise HTTPException(403, "Invalid or missing X-API-Key")
    return get_db_stats(get_config().db_path)


def start_webhook_receiver(
    host: str = "127.0.0.1",
    port: int = 8001,
    api_key: str | None = None,
    db_path: Path | None = None,
):
    set_config(WebhookConfig(db_path=db_path or Path("data/production_logs.db"), api_key=api_key))
    server = HTTPServer((host, port), WebhookRequestHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
