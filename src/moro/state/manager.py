"""
MoroAI Unified State Manager.

Provides CRUD operations for the state graph and maintains
complete lineage across all MoroAI operations.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moro.state.schema import (
    EdgeType,
    NodeStatus,
    NodeType,
    get_state_db,
    initialize_state_db,
)


class StateManager:
    """Central state manager for MoroAI.

    Maintains the state graph and provides methods for:
    - Creating and querying nodes
    - Creating and querying edges
    - Tracing lineage
    - Managing the model registry
    - Logging operations
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if not db_path.exists():
            initialize_state_db(db_path)

    def _get_conn(self):
        return get_state_db(self.db_path)

    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    # ===================================================================
    # NODE OPERATIONS
    # ===================================================================

    def create_node(
        self,
        node_type: NodeType,
        name: str,
        payload: dict[str, Any] | None = None,
        status: NodeStatus = NodeStatus.PENDING,
        parent_node_id: str | None = None,
        created_by: str = "system",
    ) -> str:
        """Create a new node in the state graph.

        Returns the generated node_id.
        """
        node_id = self._generate_id(node_type.value[:4])
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO nodes (
                    node_id, node_type, name, status,
                    payload_json, created_at, updated_at,
                    created_by, parent_node_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    node_type.value,
                    name,
                    status.value,
                    json.dumps(payload or {}),
                    now,
                    now,
                    created_by,
                    parent_node_id,
                ),
            )
            conn.commit()

            # Log the operation
            self._log_operation("create_node", node_id, f"Created {node_type.value}: {name}")

            return node_id
        finally:
            conn.close()

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM nodes WHERE node_id = ?",
                [node_id],
            ).fetchone()

            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def update_node(
        self,
        node_id: str,
        status: NodeStatus | None = None,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Update a node's status and/or payload."""
        conn = self._get_conn()
        try:
            updates = []
            params: list[Any] = []

            if status is not None:
                updates.append("status = ?")
                params.append(status.value)

            if payload is not None:
                updates.append("payload_json = ?")
                params.append(json.dumps(payload))

            if not updates:
                return False

            updates.append("updated_at = ?")
            params.append(datetime.now(timezone.utc).isoformat())
            params.append(node_id)

            conn.execute(
                f"UPDATE nodes SET {', '.join(updates)} WHERE node_id = ?",
                params,
            )
            conn.commit()

            self._log_operation("update_node", node_id, "Updated node status/payload")
            return True
        finally:
            conn.close()

    def query_nodes(
        self,
        node_type: NodeType | None = None,
        status: NodeStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query nodes with optional filters."""
        conn = self._get_conn()
        try:
            conditions = []
            params: list[Any] = []

            if node_type is not None:
                conditions.append("node_type = ?")
                params.append(node_type.value)

            if status is not None:
                conditions.append("status = ?")
                params.append(status.value)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = conn.execute(
                f"""
                SELECT * FROM nodes
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ===================================================================
    # EDGE OPERATIONS
    # ===================================================================

    def create_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        edge_type: EdgeType,
        metadata: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> str:
        """Create an edge between two nodes.

        Returns the generated edge_id.
        """
        edge_id = self._generate_id("edge")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO edges (
                    edge_id, source_node_id, target_node_id,
                    edge_type, weight, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge_id,
                    source_node_id,
                    target_node_id,
                    edge_type.value,
                    weight,
                    json.dumps(metadata or {}),
                    now,
                ),
            )
            conn.commit()
            return edge_id
        finally:
            conn.close()

    def get_connected_nodes(
        self,
        node_id: str,
        edge_type: EdgeType | None = None,
        direction: str = "both",  # "incoming", "outgoing", "both"
    ) -> list[dict[str, Any]]:
        """Get all nodes connected to a given node."""
        conn = self._get_conn()
        try:
            queries = []
            params: list[Any] = []

            if direction in ("outgoing", "both"):
                queries.append("""
                    SELECT n.*, e.edge_type, e.metadata_json as edge_metadata, 'outgoing' as direction
                    FROM nodes n
                    JOIN edges e ON n.node_id = e.target_node_id
                    WHERE e.source_node_id = ?
                """)
                params.append(node_id)

            if direction in ("incoming", "both"):
                queries.append("""
                    SELECT n.*, e.edge_type, e.metadata_json as edge_metadata, 'incoming' as direction
                    FROM nodes n
                    JOIN edges e ON n.node_id = e.source_node_id
                    WHERE e.target_node_id = ?
                """)
                params.append(node_id)

            if not queries:
                return []

            full_query = " UNION ALL ".join(queries)
            if edge_type is not None:
                full_query += f" AND edge_type = '{edge_type.value}'"

            rows = conn.execute(
                full_query,
                params * 2 if direction == "both" else params,
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    # ===================================================================
    # LINEAGE TRACING
    # ===================================================================

    def trace_lineage(self, node_id: str, max_depth: int = 10) -> dict[str, Any]:
        """Trace the complete lineage of a node.

        Returns a tree structure showing all ancestors and descendants.
        """
        visited_up: set[str] = set()
        visited_down: set[str] = set()

        def _trace_up(nid: str, depth: int) -> list[dict[str, Any]]:
            if depth > max_depth or nid in visited_up:
                return []

            visited_up.add(nid)
            node = self.get_node(nid)
            if not node:
                return []

            parents = self.get_connected_nodes(nid, direction="incoming")
            result = {
                "node": node,
                "parents": [_trace_up(p["node_id"], depth + 1) for p in parents],
            }
            return [result]

        def _trace_down(nid: str, depth: int) -> list[dict[str, Any]]:
            if depth > max_depth or nid in visited_down:
                return []

            visited_down.add(nid)
            node = self.get_node(nid)
            if not node:
                return []

            children = self.get_connected_nodes(nid, direction="outgoing")
            result = {
                "node": node,
                "children": [_trace_down(c["node_id"], depth + 1) for c in children],
            }
            return [result]

        return {
            "node_id": node_id,
            "ancestors": _trace_up(node_id, 0),
            "descendants": _trace_down(node_id, 0),
        }

    # ===================================================================
    # MODEL REGISTRY OPERATIONS
    # ===================================================================

    def register_model(
        self,
        model_name: str,
        version: str,
        base_model: str,
        training_run_id: str | None = None,
        dataset_version_id: str | None = None,
        quantization: str | None = None,
        adapter_type: str | None = None,
        lora_rank: int | None = None,
    ) -> str:
        """Register a new model in the registry."""
        model_id = self._generate_id("model")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            # Record release node in nodes table
            conn.execute(
                """
                INSERT OR IGNORE INTO nodes (
                    node_id, node_type, name, status, payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'completed', ?, ?, ?)
                """,
                (
                    model_id,
                    NodeType.RELEASE.value,
                    f"{model_name}:{version}",
                    json.dumps({"base_model": base_model, "quantization": quantization}),
                    now,
                    now,
                ),
            )

            conn.execute(
                """
                INSERT OR REPLACE INTO model_registry (
                    model_id, model_name, version, base_model,
                    training_run_id, dataset_version_id,
                    quantization, adapter_type, lora_rank,
                    status, trained_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'trained', ?)
                """,
                (
                    model_id,
                    model_name,
                    version,
                    base_model,
                    training_run_id,
                    dataset_version_id,
                    quantization,
                    adapter_type,
                    lora_rank,
                    now,
                ),
            )
            conn.commit()

            self._log_operation("register_model", model_id, f"Registered {model_name}:{version}")
            return model_id
        finally:
            conn.close()

    def get_model(self, model_name: str, version: str | None = None) -> dict[str, Any] | None:
        """Get a model from the registry."""
        conn = self._get_conn()
        try:
            if version:
                row = conn.execute(
                    "SELECT * FROM model_registry WHERE model_name = ? AND version = ?",
                    [model_name, version],
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM model_registry WHERE model_name = ? ORDER BY trained_at DESC LIMIT 1",
                    [model_name],
                ).fetchone()

            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def list_models(
        self,
        status: str | None = None,
        production_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List all models in the registry."""
        conn = self._get_conn()
        try:
            conditions = []
            params: list[Any] = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            if production_only:
                conditions.append("is_production = 1")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = conn.execute(
                f"""
                SELECT * FROM model_registry
                {where_clause}
                ORDER BY trained_at DESC
                """,
                params,
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def promote_model_to_production(self, model_id: str) -> bool:
        """Promote a model to production (demotes current production model)."""
        conn = self._get_conn()
        try:
            # Demote current production model
            conn.execute("UPDATE model_registry SET is_production = 0 WHERE is_production = 1")

            # Promote new model
            conn.execute(
                "UPDATE model_registry SET is_production = 1, status = 'deployed' WHERE model_id = ?",
                [model_id],
            )
            conn.commit()

            self._log_operation("promote_model", model_id, "Promoted to production")
            return True
        finally:
            conn.close()

    # ===================================================================
    # OPERATION LOGGING
    # ===================================================================

    def _log_operation(
        self,
        operation_type: str,
        node_id: str | None,
        description: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Log an operation to the audit trail."""
        log_id = self._generate_id("oplog")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            valid_node_id = None
            if node_id:
                row = conn.execute("SELECT 1 FROM nodes WHERE node_id = ?", [node_id]).fetchone()
                if row:
                    valid_node_id = node_id

            conn.execute(
                """
                INSERT INTO operation_log (
                    log_id, operation_type, node_id,
                    description, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    log_id,
                    operation_type,
                    valid_node_id,
                    description,
                    json.dumps(payload or {}),
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_operation_log(
        self,
        node_id: str | None = None,
        operation_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get operation log entries."""
        conn = self._get_conn()
        try:
            conditions = []
            params: list[Any] = []

            if node_id:
                conditions.append("node_id = ?")
                params.append(node_id)

            if operation_type:
                conditions.append("operation_type = ?")
                params.append(operation_type)

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = conn.execute(
                f"""
                SELECT * FROM operation_log
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()
