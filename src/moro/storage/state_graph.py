"""
MoroAI Unified State Graph.

Maintains end-to-end cryptographic and metadata lineage across:
raw_source → dataset_version → training_run → eval_result → release → deployment → feedback
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moro.core.paths import find_project_root


class StateGraphManager:
    """Manages the full end-to-end lineage state graph for a MoroAI project."""

    def __init__(self, db_path: Path | None = None) -> None:
        if db_path is None:
            root = find_project_root() or Path.cwd()
            db_dir = root / ".moro"
            db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = db_dir / "state_graph.db"
        else:
            self.db_path = db_path

        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS lineage_nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    parent_id TEXT,
                    name TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_lineage_parent ON lineage_nodes(parent_id)
                """
            )
            conn.commit()
        finally:
            conn.close()

    def record_node(
        self,
        node_id: str,
        node_type: str,
        parent_id: str | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a node in the state lineage graph."""
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata or {})
        display_name = name or f"{node_type}:{node_id}"

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO lineage_nodes (
                    id, node_type, parent_id, name, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (node_id, node_type, parent_id, display_name, meta_str, now),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            "id": node_id,
            "node_type": node_type,
            "parent_id": parent_id,
            "name": display_name,
            "metadata": metadata or {},
            "created_at": now,
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Fetch details of a single lineage node."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute("SELECT * FROM lineage_nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return None
            data = dict(row)
            data["metadata"] = json.loads(data.get("metadata_json") or "{}")
            return data
        finally:
            conn.close()

    def get_ancestors(self, node_id: str) -> list[dict[str, Any]]:
        """Trace lineage backwards from node to the raw source ancestor."""
        ancestors = []
        curr_id: str | None = node_id
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            while curr_id:
                row = conn.execute(
                    "SELECT * FROM lineage_nodes WHERE id = ?", (curr_id,)
                ).fetchone()
                if not row:
                    break
                node_data = dict(row)
                node_data["metadata"] = json.loads(node_data.get("metadata_json") or "{}")
                ancestors.append(node_data)
                curr_id = node_data.get("parent_id")
        finally:
            conn.close()

        ancestors.reverse()
        return ancestors

    def get_graph(self) -> dict[str, Any]:
        """Return all nodes and directed edges for UI visualization."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM lineage_nodes ORDER BY created_at ASC").fetchall()
            nodes = []
            edges = []
            for r in rows:
                n = dict(r)
                n["metadata"] = json.loads(n.get("metadata_json") or "{}")
                nodes.append(n)
                if n.get("parent_id"):
                    edges.append({"source": n["parent_id"], "target": n["id"]})
            return {"nodes": nodes, "edges": edges}
        finally:
            conn.close()

    def get_summary(self) -> dict[str, int]:
        """Return counts of lineage items by node_type."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT node_type, COUNT(*) FROM lineage_nodes GROUP BY node_type"
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            conn.close()
