"""
MoroAI Experiment Tracking Schema.

Defines the database schema for storing experiment metrics,
hyperparameters, and time-series data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

EXPERIMENT_TRACKING_SCHEMA = """
-- Experiments table: One row per training run
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id     TEXT PRIMARY KEY,
    experiment_name   TEXT NOT NULL,

    -- Status
    status            TEXT NOT NULL DEFAULT 'pending',
    -- pending, running, completed, failed, cancelled

    -- Timing
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    started_at        TEXT,
    completed_at      TEXT,
    duration_seconds  REAL,

    -- Model info
    base_model        TEXT NOT NULL,
    model_class       TEXT,
    quantization      TEXT,

    -- Dataset info
    dataset_id        TEXT,
    dataset_name      TEXT,
    dataset_tokens    INTEGER,
    dataset_samples   INTEGER,

    -- Hardware info
    gpu_name          TEXT,
    gpu_vram_gb       REAL,
    peak_vram_gb      REAL,

    -- Final metrics
    final_train_loss  REAL,
    final_eval_loss   REAL,
    eval_pass_rate    REAL,
    eval_delta        REAL,

    -- Resource utilization
    total_steps       INTEGER,
    tokens_per_second REAL,

    -- Tags and metadata
    tags_json         TEXT DEFAULT '[]',
    notes             TEXT,

    -- Lineage
    parent_experiment_id TEXT,
    state_node_id     TEXT,

    FOREIGN KEY (parent_experiment_id) REFERENCES experiments (experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_exp_status ON experiments (status);
CREATE INDEX IF NOT EXISTS idx_exp_created ON experiments (created_at);
CREATE INDEX IF NOT EXISTS idx_exp_model ON experiments (base_model);
CREATE INDEX IF NOT EXISTS idx_exp_dataset ON experiments (dataset_id);

-- Hyperparameters table: Complete config snapshot per experiment
CREATE TABLE IF NOT EXISTS hyperparameters (
    param_id          TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL,

    -- Core hyperparameters
    learning_rate     REAL,
    batch_size        INTEGER,
    gradient_accumulation_steps INTEGER,
    epochs            REAL,
    warmup_ratio      REAL,
    weight_decay      REAL,

    -- LoRA hyperparameters
    lora_r            INTEGER,
    lora_alpha        INTEGER,
    lora_dropout      REAL,
    target_modules_json TEXT,

    -- Training configuration
    optimizer         TEXT,
    scheduler         TEXT,
    max_seq_length    INTEGER,
    gradient_checkpointing INTEGER,

    -- Regularization
    kl_penalty_beta   REAL,
    replay_ratio      REAL,

    -- Advanced
    seed              INTEGER,
    fp16              INTEGER,
    bf16              INTEGER,

    -- Full config snapshot (JSON)
    full_config_json  TEXT,

    created_at        TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_hp_experiment ON hyperparameters (experiment_id);

-- Metrics table: Time-series metrics per step
CREATE TABLE IF NOT EXISTS metrics (
    metric_id         TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL,

    -- Step info
    step              INTEGER NOT NULL,
    epoch             REAL,
    timestamp         TEXT NOT NULL DEFAULT (datetime('now')),

    -- Loss metrics
    train_loss        REAL,
    eval_loss         REAL,
    kl_divergence     REAL,

    -- Gradient metrics
    grad_norm         REAL,
    update_ratio      REAL,

    -- Learning rate
    learning_rate     REAL,

    -- Resource metrics
    vram_allocated_gb REAL,
    vram_reserved_gb  REAL,
    gpu_utilization   REAL,
    cpu_utilization   REAL,

    -- Throughput
    tokens_per_second REAL,
    samples_per_second REAL,

    -- Anomaly flags
    is_anomaly        INTEGER DEFAULT 0,
    anomaly_type      TEXT,

    FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_metrics_experiment ON metrics (experiment_id);
CREATE INDEX IF NOT EXISTS idx_metrics_step ON metrics (experiment_id, step);
CREATE INDEX IF NOT EXISTS idx_metrics_anomaly ON metrics (is_anomaly);

-- Eval results table: Detailed evaluation outcomes
CREATE TABLE IF NOT EXISTS eval_results (
    eval_id           TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL,

    -- Eval suite info
    suite_name        TEXT NOT NULL,
    suite_version     TEXT,

    -- Results
    total_cases       INTEGER,
    passed_cases      INTEGER,
    failed_cases      INTEGER,
    pass_rate         REAL,

    -- Comparison (if base model was also evaluated)
    base_pass_rate    REAL,
    pass_rate_delta   REAL,

    -- Drift metrics
    verbosity_drift   REAL,
    tone_drift        REAL,
    semantic_drift    REAL,

    -- Safety
    safety_pass_rate  REAL,
    hallucination_count INTEGER,

    -- Detailed results (JSON array of per-case results)
    case_results_json TEXT,

    -- Timestamp
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_experiment ON eval_results (experiment_id);
CREATE INDEX IF NOT EXISTS idx_eval_suite ON eval_results (suite_name);

-- Model outputs table: Sample outputs for comparison
CREATE TABLE IF NOT EXISTS model_outputs (
    output_id         TEXT PRIMARY KEY,
    experiment_id     TEXT NOT NULL,

    -- Prompt info
    prompt            TEXT NOT NULL,
    prompt_category   TEXT,

    -- Output
    completion        TEXT NOT NULL,

    -- Metadata
    latency_ms        REAL,
    token_count       INTEGER,

    -- Evaluation
    eval_score        REAL,
    eval_passed       INTEGER,

    created_at        TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (experiment_id) REFERENCES experiments (experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_output_experiment ON model_outputs (experiment_id);
CREATE INDEX IF NOT EXISTS idx_output_prompt ON model_outputs (prompt_category);

-- Recommendations table: Suggested next experiments
CREATE TABLE IF NOT EXISTS recommendations (
    rec_id            TEXT PRIMARY KEY,

    -- Context
    based_on_experiments_json TEXT,  -- List of experiment IDs analyzed

    -- Recommendation
    rec_type          TEXT NOT NULL,
    -- hyperparameter_change, dataset_change, architecture_change, stop_training

    description       TEXT NOT NULL,
    suggested_config_json TEXT,

    -- Confidence
    confidence        REAL,
    reasoning         TEXT,

    -- Status
    status            TEXT DEFAULT 'pending',
    -- pending, accepted, rejected, applied

    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_rec_status ON recommendations (status);
CREATE INDEX IF NOT EXISTS idx_rec_type ON recommendations (rec_type);
"""


def initialize_experiment_db(db_path: Path) -> sqlite3.Connection:
    """Initialize the experiment tracking database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    conn.executescript(EXPERIMENT_TRACKING_SCHEMA)
    conn.commit()

    return conn


def get_experiment_db(db_path: Path) -> sqlite3.Connection:
    """Get a connection to the experiment database."""
    if not db_path.exists():
        raise FileNotFoundError(f"Experiment database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn
