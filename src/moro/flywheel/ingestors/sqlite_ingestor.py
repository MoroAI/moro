"""
MoroAI SQLite Log Ingestor.

Concrete implementation of AbstractLogIngestor that reads and writes
production inference logs from a local SQLite database with strict idempotency.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from moro.flywheel.architecture import AbstractLogIngestor
from moro.flywheel.models import InferenceLogPayload
from moro.flywheel.storage.schema import get_production_db


class SQLiteLogIngestor(AbstractLogIngestor):
    """
    Ingests production inference logs from a SQLite database idempotently.
    Once marked as processed, a log is never ingested again.
    """

    def __init__(
        self,
        db_path: Path,
        batch_size: int = 100,
        include_positive: bool = True,
        include_negative: bool = True,
        include_corrections: bool = True,
    ):
        self.db_path = Path(db_path)
        self.batch_size = batch_size
        self.include_positive = include_positive
        self.include_negative = include_negative
        self.include_corrections = include_corrections

    def _build_query(self) -> tuple[str, list]:
        conditions = ["is_processed = 0"]
        signal_conditions = []

        if self.include_corrections:
            signal_conditions.append(
                "human_correction IS NOT NULL AND length(trim(human_correction)) > 0"
            )

        if self.include_negative:
            signal_conditions.append("user_rating IS NOT NULL AND user_rating < 0")

        if self.include_positive:
            signal_conditions.append("user_rating IS NOT NULL AND user_rating > 0")

        if signal_conditions:
            conditions.append(f"({' OR '.join(signal_conditions)})")

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT 
                log_id,
                session_id,
                prompt,
                completion,
                context,
                user_rating,
                human_correction,
                latency_ms,
                metadata_json,
                created_at
            FROM inference_logs
            WHERE {where_clause}
            ORDER BY created_at ASC
            LIMIT ?
        """
        return query, [self.batch_size]

    def ingest_logs(self, source_path: Path | None = None) -> list[InferenceLogPayload]:
        """Ingest unprocessed logs from the SQLite database."""
        db_path = source_path if source_path is not None else self.db_path
        conn = get_production_db(db_path)
        try:
            query, params = self._build_query()
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

            logs: list[InferenceLogPayload] = []
            for row in rows:
                try:
                    metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

                # Store log_id inside metadata so downstream extractors can track source log id
                metadata["log_id"] = row["log_id"]

                try:
                    ts = datetime.fromisoformat(row["created_at"])
                except (ValueError, TypeError):
                    ts = datetime.now(timezone.utc)

                log = InferenceLogPayload(
                    session_id=row["session_id"],
                    prompt=row["prompt"],
                    completion=row["completion"],
                    context=row["context"],
                    user_rating=row["user_rating"],
                    human_correction=row["human_correction"],
                    latency_ms=row["latency_ms"],
                    metadata=metadata,
                    timestamp=ts,
                )
                logs.append(log)
            return logs
        finally:
            conn.close()

    def mark_processed(
        self,
        session_ids: list[str],
        epoch_id: str,
        log_ids: list[str] | None = None,
    ) -> int:
        """Mark logs as processed to ensure idempotent extraction."""
        conn = get_production_db(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            if log_ids:
                placeholders = ",".join(["?" for _ in log_ids])
                cursor = conn.execute(
                    f"""
                    UPDATE inference_logs
                    SET is_processed = 1,
                        processed_at = ?,
                        epoch_id = ?
                    WHERE log_id IN ({placeholders})
                    AND is_processed = 0
                    """,
                    [now, epoch_id] + log_ids,
                )
            elif session_ids:
                placeholders = ",".join(["?" for _ in session_ids])
                cursor = conn.execute(
                    f"""
                    UPDATE inference_logs
                    SET is_processed = 1,
                        processed_at = ?,
                        epoch_id = ?
                    WHERE session_id IN ({placeholders})
                    AND is_processed = 0
                    """,
                    [now, epoch_id] + session_ids,
                )
            else:
                return 0

            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def get_pending_count(self) -> int:
        """Get the number of unprocessed logs waiting in the database."""
        conn = get_production_db(self.db_path)
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) as count FROM inference_logs WHERE is_processed = 0"
            )
            row = cursor.fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    def insert_log(self, payload: InferenceLogPayload) -> str:
        """Insert a single inference log into SQLite."""
        log_id = payload.metadata.get("log_id") or str(uuid.uuid4())
        conn = get_production_db(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO inference_logs (
                    log_id, session_id, model_name, prompt, completion,
                    context, user_rating, human_correction, latency_ms,
                    metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    payload.session_id,
                    payload.metadata.get("model_name", "production"),
                    payload.prompt,
                    payload.completion,
                    payload.context,
                    payload.user_rating,
                    payload.human_correction,
                    payload.latency_ms,
                    json.dumps(payload.metadata),
                    payload.timestamp.isoformat(),
                ),
            )
            conn.commit()
            return log_id
        finally:
            conn.close()

    def insert_logs_from_jsonl(self, jsonl_path: Path) -> int:
        """Import logs from a JSONL file into the SQLite database."""
        if not jsonl_path.exists():
            raise FileNotFoundError(f"File not found: {jsonl_path}")

        count = 0
        with jsonl_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                # Map various schema formats (FeedbackEntry, InferenceLogPayload, or raw)
                session_id = data.get("session_id", f"import_{uuid.uuid4().hex[:8]}")
                prompt = data.get("prompt") or data.get("user_prompt") or ""
                completion = data.get("completion") or data.get("model_response") or ""
                context = data.get("context")
                rating = data.get("user_rating")
                if rating is None and "implicit_signal" in data:
                    sig = data["implicit_signal"]
                    rating = (
                        1.0
                        if sig == "positive"
                        else -1.0
                        if sig in ("negative", "regenerate")
                        else None
                    )
                correction = data.get("human_correction")
                latency = data.get("latency_ms")

                if prompt and completion:
                    payload = InferenceLogPayload(
                        session_id=session_id,
                        prompt=prompt,
                        completion=completion,
                        context=context,
                        user_rating=rating,
                        human_correction=correction,
                        latency_ms=latency,
                        metadata=data.get("metadata", {}),
                    )
                    self.insert_log(payload)
                    count += 1
        return count

    def get_epoch_history(self, epoch_id: str) -> dict:
        """Get metadata about a specific DPO epoch."""
        conn = get_production_db(self.db_path)
        try:
            epoch_row = conn.execute(
                "SELECT * FROM dpo_epochs WHERE epoch_id = ?",
                [epoch_id],
            ).fetchone()
            if not epoch_row:
                return {}

            pair_count = conn.execute(
                "SELECT COUNT(*) as count FROM preference_pairs WHERE epoch_id = ?",
                [epoch_id],
            ).fetchone()["count"]

            log_count = conn.execute(
                "SELECT COUNT(*) as count FROM inference_logs WHERE epoch_id = ?",
                [epoch_id],
            ).fetchone()["count"]

            return {
                "epoch_id": epoch_id,
                "status": epoch_row["status"],
                "initial_loss": epoch_row["initial_loss"],
                "final_loss": epoch_row["final_loss"],
                "pair_count": pair_count,
                "log_count": log_count,
                "deployed": bool(epoch_row["deployed"]),
                "started_at": epoch_row["started_at"],
                "completed_at": epoch_row["completed_at"],
            }
        finally:
            conn.close()

    def list_epochs(self, limit: int = 20) -> list[dict]:
        """List recent DPO epochs."""
        conn = get_production_db(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT epoch_id, status, initial_loss, final_loss, pair_count, deployed, started_at, completed_at
                FROM dpo_epochs
                ORDER BY started_at DESC, epoch_id DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
