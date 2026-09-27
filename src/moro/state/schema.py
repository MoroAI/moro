"""
MoroAI Unified State Manager Schema.

Defines the SQLite schema for the state graph that maintains
complete lineage across all MoroAI operations.
"""

from __future__ import annotations

import sqlite3
from enum import Enum
from pathlib import Path


class NodeType(str, Enum):
    """Types of nodes in the state graph."""

    RAW_SOURCE = "raw_source"
    DATASET_VERSION = "dataset_version"
    TRAINING_RUN = "training_run"
    EVAL_RESULT = "eval_result"
    RELEASE = "release"
    DEPLOYMENT = "deployment"
    FEEDBACK_BATCH = "feedback_batch"
    DPO_EPOCH = "dpo_epoch"
    RECIPE = "recipe"
    CONFIG_SNAPSHOT = "config_snapshot"


class EdgeType(str, Enum):
    """Types of edges in the state graph."""

    DERIVED_FROM = "derived_from"
    TRAINED_ON = "trained_on"
    EVALUATED_BY = "evaluated_by"
    RELEASED_FROM = "released_from"
    DEPLOYED_FROM = "deployed_from"
    FEEDBACK_FOR = "feedback_for"
    ALIGNED_BY = "aligned_by"
    USED_RECIPE = "used_recipe"
    USED_CONFIG = "used_config"
    SUPERSEDES = "supersedes"  # For model versioning


class NodeStatus(str, Enum):
    """Status of a node in the state graph."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"
    DEPLOYED = "deployed"
    ROLLED_BACK = "rolled_back"


# Complete DDL for the state graph database
STATE_GRAPH_SCHEMA = """
-- Nodes table: Every entity in the system
CREATE TABLE IF NOT EXISTS nodes (
    node_id         TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    name            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',

    -- Payload: JSON blob with type-specific data
    payload_json    TEXT DEFAULT '{}',

    -- Lineage metadata
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT DEFAULT 'system',

    -- Versioning
    version         INTEGER NOT NULL DEFAULT 1,
    parent_node_id  TEXT,

    FOREIGN KEY (parent_node_id) REFERENCES nodes (node_id)
);

-- Edges table: Relationships between nodes
CREATE TABLE IF NOT EXISTS edges (
    edge_id         TEXT PRIMARY KEY,
    source_node_id  TEXT NOT NULL,
    target_node_id  TEXT NOT NULL,
    edge_type       TEXT NOT NULL,

    -- Edge metadata
    weight          REAL DEFAULT 1.0,
    metadata_json   TEXT DEFAULT '{}',

    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (source_node_id) REFERENCES nodes (node_id),
    FOREIGN KEY (target_node_id) REFERENCES nodes (node_id),

    -- Prevent duplicate edges of the same type between same nodes
    UNIQUE (source_node_id, target_node_id, edge_type)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes (node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes (status);
CREATE INDEX IF NOT EXISTS idx_nodes_created ON nodes (created_at);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes (parent_node_id);

CREATE INDEX IF NOT EXISTS idx_edges_source ON edges (source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges (target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges (edge_type);

-- Model Registry: Quick lookup for deployed models
CREATE TABLE IF NOT EXISTS model_registry (
    model_id        TEXT PRIMARY KEY,
    model_name      TEXT NOT NULL,
    version         TEXT NOT NULL,
    base_model      TEXT NOT NULL,

    -- References to state graph
    training_run_id TEXT,
    release_id      TEXT,
    deployment_id   TEXT,

    -- Model metadata
    quantization    TEXT,
    adapter_type    TEXT,
    lora_rank       INTEGER,

    -- Eval summary
    eval_pass_rate  REAL,
    eval_delta      REAL,

    -- Status
    status          TEXT NOT NULL DEFAULT 'trained',
    is_production   INTEGER NOT NULL DEFAULT 0,

    -- Timestamps
    trained_at      TEXT,
    released_at     TEXT,
    deployed_at     TEXT,

    -- Lineage
    dataset_version_id TEXT,

    UNIQUE (model_name, version)
);

CREATE INDEX IF NOT EXISTS idx_registry_name ON model_registry (model_name);
CREATE INDEX IF NOT EXISTS idx_registry_status ON model_registry (status);
CREATE INDEX IF NOT EXISTS idx_registry_production ON model_registry (is_production);

-- Operation Log: Audit trail of all state changes
CREATE TABLE IF NOT EXISTS operation_log (
    log_id          TEXT PRIMARY KEY,
    operation_type  TEXT NOT NULL,
    node_id         TEXT,

    -- Operation details
    description     TEXT,
    payload_json    TEXT DEFAULT '{}',

    -- Context
    user_id         TEXT DEFAULT 'system',
    session_id      TEXT,

    created_at      TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (node_id) REFERENCES nodes (node_id)
);

CREATE INDEX IF NOT EXISTS idx_oplog_node ON operation_log (node_id);
CREATE INDEX IF NOT EXISTS idx_oplog_type ON operation_log (operation_type);
CREATE INDEX IF NOT EXISTS idx_oplog_created ON operation_log (created_at);

-- Service State: Tracks running services
CREATE TABLE IF NOT EXISTS service_state (
    service_id      TEXT PRIMARY KEY,
    service_name    TEXT NOT NULL UNIQUE,
    service_type    TEXT NOT NULL,

    -- Process info
    pid             INTEGER,
    port            INTEGER,
    host            TEXT,

    -- Status
    status          TEXT NOT NULL DEFAULT 'stopped',
    health_status   TEXT DEFAULT 'unknown',

    -- Timestamps
    started_at      TEXT,
    stopped_at      TEXT,
    last_health_check TEXT,

    -- Configuration
    config_json     TEXT DEFAULT '{}',

    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_service_name ON service_state (service_name);
CREATE INDEX IF NOT EXISTS idx_service_status ON service_state (status);
"""


def initialize_state_db(db_path: Path) -> sqlite3.Connection:
    """
    Initialize the state graph database.
    Safe to call multiple times (idempotent).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(STATE_GRAPH_SCHEMA)
    conn.commit()

    return conn


def get_state_db(db_path: Path) -> sqlite3.Connection:
    """Get a connection to an existing state database."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"State database not found at {db_path}. "
            "Run 'moro init' to initialize the project."
        )

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn
