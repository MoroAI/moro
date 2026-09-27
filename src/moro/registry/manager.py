"""
MoroAI Model Registry Manager.

Provides searchable, queryable tracking of trained model versions,
evaluation scores, tags (candidate, staging, production), and lineage.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moro.core.paths import find_project_root


class ModelRegistry:
    """SQLite-backed Model Registry for MoroAI."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            root = find_project_root() or Path.cwd()
            db_dir = root / ".moro"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "registry.db"
        else:
            self.db_path = db_path

        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS registered_models (
                    model_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    base_model TEXT NOT NULL,
                    tag TEXT NOT NULL DEFAULT 'candidate',
                    val_loss REAL,
                    pass_rate REAL,
                    artifact_path TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_registry_tag ON registered_models(tag)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def register_model(
        self,
        model_id: str,
        name: str,
        run_id: str,
        base_model: str,
        artifact_path: str = "",
        val_loss: float | None = None,
        pass_rate: float | None = None,
        tag: str = "candidate",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a new model version."""
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata or {})

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO registered_models (
                    model_id, name, run_id, base_model, tag, val_loss, pass_rate,
                    artifact_path, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    name,
                    run_id,
                    base_model,
                    tag,
                    val_loss,
                    pass_rate,
                    artifact_path,
                    meta_str,
                    now,
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "model_id": model_id,
            "name": name,
            "run_id": run_id,
            "base_model": base_model,
            "tag": tag,
            "val_loss": val_loss,
            "pass_rate": pass_rate,
            "artifact_path": artifact_path,
            "metadata": metadata or {},
            "created_at": now,
        }

    def list_models(self, tag: str | None = None) -> list[dict[str, Any]]:
        """List registered models, optionally filtered by tag."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if tag:
                rows = conn.execute(
                    "SELECT * FROM registered_models WHERE tag = ? ORDER BY updated_at DESC",
                    (tag,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM registered_models ORDER BY updated_at DESC"
                ).fetchall()

            models = []
            for r in rows:
                item = dict(r)
                item["metadata"] = json.loads(item.get("metadata_json") or "{}")
                models.append(item)
            return models
        finally:
            conn.close()

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        """Fetch details of a single registered model."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM registered_models WHERE model_id = ?",
                (model_id,),
            ).fetchone()
            if not row:
                return None
            item = dict(row)
            item["metadata"] = json.loads(item.get("metadata_json") or "{}")
            return item
        finally:
            conn.close()

    def promote_model(self, model_id: str, target_tag: str = "production") -> bool:
        """Promote a model to a target tag (e.g. staging or production)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "UPDATE registered_models SET tag = ?, updated_at = ? WHERE model_id = ?",
                (target_tag, now, model_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_model(self, model_id: str) -> bool:
        """Remove a model from the registry."""
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "DELETE FROM registered_models WHERE model_id = ?",
                (model_id,),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
