"""
Tests for MoroAI Experiment Tracking & Visual Analytics Engine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from moro.analytics.schema import get_experiment_db, initialize_experiment_db
from moro.analytics.tracker import ExperimentTracker
from moro.analytics.visualizations import VisualAnalyticsEngine
from moro.cli.analytics import analytics_app
from moro.dashboard.mission_control import app as dashboard_app
from moro.training.runner import TrainingRunner

runner = CliRunner(env={"COLUMNS": "160"})


@pytest.fixture
def analytics_db_path(tmp_path: Path) -> Path:
    return tmp_path / ".moro" / "analytics.db"


@pytest.fixture
def tracker(analytics_db_path: Path) -> ExperimentTracker:
    return ExperimentTracker(analytics_db_path)


# ===================================================================
# 1. DATABASE SCHEMA & INITIALIZATION
# ===================================================================


def test_initialize_experiment_db(analytics_db_path: Path):
    """Test SQLite initialization and schema creation."""
    conn = initialize_experiment_db(analytics_db_path)
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in tables}

        expected = {
            "experiments",
            "hyperparameters",
            "metrics",
            "eval_results",
            "model_outputs",
            "recommendations",
        }
        assert expected.issubset(table_names)
    finally:
        conn.close()

    # Reopening should work
    reopened = get_experiment_db(analytics_db_path)
    try:
        row = reopened.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
    finally:
        reopened.close()


# ===================================================================
# 2. EXPERIMENT LIFECYCLE
# ===================================================================


def test_experiment_lifecycle(tracker: ExperimentTracker):
    """Test full lifecycle: create -> start -> log -> complete."""
    exp_id = tracker.create_experiment(
        name="test_run_001",
        base_model="Qwen/Qwen2.5-1.5B",
        dataset_id="ds_abc123",
        dataset_name="train.jsonl",
        tags=["lora", "quantum"],
        notes="Testing lifecycle",
    )
    assert exp_id.startswith("exp_")

    exp = tracker.get_experiment(exp_id)
    assert exp is not None
    assert exp["experiment_name"] == "test_run_001"
    assert exp["status"] == "pending"
    assert json.loads(exp["tags_json"]) == ["lora", "quantum"]

    # Start experiment
    hp = {
        "learning_rate": 2e-4,
        "batch_size": 4,
        "gradient_accumulation_steps": 2,
        "epochs": 3.0,
        "warmup_ratio": 0.05,
        "weight_decay": 0.01,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "target_modules": ["q_proj", "v_proj"],
        "optimizer": "adamw_8bit",
        "max_seq_length": 1024,
    }
    tracker.start_experiment(
        experiment_id=exp_id,
        hyperparameters=hp,
        gpu_name="NVIDIA A100",
        gpu_vram_gb=80.0,
    )

    exp_after_start = tracker.get_experiment(exp_id)
    assert exp_after_start["status"] == "running"
    assert exp_after_start["gpu_name"] == "NVIDIA A100"

    recorded_hp = tracker.get_hyperparameters(exp_id)
    assert recorded_hp is not None
    assert recorded_hp["learning_rate"] == 2e-4
    assert recorded_hp["lora_r"] == 16
    assert recorded_hp["target_modules"] == ["q_proj", "v_proj"]

    # Log metrics
    for step in range(1, 4):
        tracker.log_metrics(
            experiment_id=exp_id,
            step=step * 10,
            epoch=step * 0.5,
            train_loss=2.5 - (step * 0.3),
            eval_loss=2.6 - (step * 0.25),
            grad_norm=1.2,
            learning_rate=2e-4,
            vram_allocated_gb=12.4,
            tokens_per_second=1500.0,
            is_anomaly=(step == 2),
            anomaly_type="loss_spike" if step == 2 else None,
        )

    metrics = tracker.get_metrics(exp_id)
    assert len(metrics) == 3
    assert metrics[0]["step"] == 10
    assert metrics[1]["is_anomaly"] == 1
    assert metrics[1]["anomaly_type"] == "loss_spike"

    # Complete experiment
    tracker.complete_experiment(
        experiment_id=exp_id,
        final_train_loss=1.6,
        final_eval_loss=1.85,
        eval_pass_rate=0.88,
        eval_delta=0.08,
        peak_vram_gb=14.2,
        total_steps=30,
        tokens_per_second=1520.0,
    )

    completed_exp = tracker.get_experiment(exp_id)
    assert completed_exp["status"] == "completed"
    assert completed_exp["final_train_loss"] == 1.6
    assert completed_exp["eval_pass_rate"] == 0.88
    assert completed_exp["eval_delta"] == 0.08
    assert completed_exp["duration_seconds"] is not None


def test_experiment_failure(tracker: ExperimentTracker):
    """Test marking an experiment as failed."""
    exp_id = tracker.create_experiment(
        name="failing_run",
        base_model="Qwen/Qwen2.5-1.5B",
    )
    tracker.start_experiment(exp_id, {"learning_rate": 1e-4})
    tracker.fail_experiment(exp_id, error_message="CUDA out of memory (OOM)")

    exp = tracker.get_experiment(exp_id)
    assert exp["status"] == "failed"
    assert "CUDA out of memory" in exp["notes"]


# ===================================================================
# 3. MULTI-EXPERIMENT COMPARISON & BEST SELECTION
# ===================================================================


def test_compare_experiments(tracker: ExperimentTracker):
    """Test multi-run comparison and automated best experiment identification."""
    # Exp 1: Higher delta, good loss
    exp1 = tracker.create_experiment(name="run_1", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp1, {"learning_rate": 2e-4, "lora_r": 16, "batch_size": 4})
    tracker.complete_experiment(
        exp1,
        final_train_loss=1.2,
        final_eval_loss=1.3,
        eval_pass_rate=0.85,
        eval_delta=0.09,
        peak_vram_gb=12.0,
        total_steps=100,
    )

    # Exp 2: Lower delta, different learning rate
    exp2 = tracker.create_experiment(name="run_2", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp2, {"learning_rate": 1e-4, "lora_r": 8, "batch_size": 4})
    tracker.complete_experiment(
        exp2,
        final_train_loss=1.5,
        final_eval_loss=1.6,
        eval_pass_rate=0.78,
        eval_delta=0.03,
        peak_vram_gb=10.0,
        total_steps=100,
    )

    comparison = tracker.compare_experiments([exp1, exp2])
    assert "error" not in comparison
    assert len(comparison["experiments"]) == 2

    # Check hyperparameter diffs
    hp_diffs = comparison["hyperparameter_differences"]
    assert "learning_rate" in hp_diffs
    assert "lora_r" in hp_diffs
    assert "batch_size" not in hp_diffs  # same in both

    # Best experiment should be exp1 (higher delta and pass rate)
    assert comparison["best_experiment_id"] == exp1


# ===================================================================
# 4. RECOMMENDATIONS & CORRELATION ANALYSIS
# ===================================================================


def test_recommendations_and_heuristics(tracker: ExperimentTracker):
    """Test autonomous recommendation generation."""
    # Seed 3 experiments with different learning rates
    lrs = [1e-4, 2e-4, 5e-4]
    deltas = [0.03, 0.08, 0.01]  # 2e-4 is best

    for i, (lr, delta) in enumerate(zip(lrs, deltas)):
        exp_id = tracker.create_experiment(name=f"run_opt_{i}", base_model="Qwen/Qwen2.5-1.5B")
        tracker.start_experiment(exp_id, {"learning_rate": lr, "lora_r": 16})
        tracker.complete_experiment(
            exp_id, final_train_loss=1.5, eval_delta=delta, eval_pass_rate=0.8
        )

    recs = tracker.generate_recommendations(recent_experiments=5)
    assert len(recs) > 0

    lr_rec = next(
        (r for r in recs if r.get("suggested_config", {}).get("learning_rate") == 2e-4), None
    )
    assert lr_rec is not None
    assert lr_rec["rec_type"] == "hyperparameter_change"


def test_failure_pattern_recommendation(tracker: ExperimentTracker):
    """Test OOM pattern detection."""
    for i in range(2):
        exp_id = tracker.create_experiment(name=f"run_fail_{i}", base_model="Qwen/Qwen2.5-1.5B")
        tracker.start_experiment(exp_id, {"batch_size": 8, "max_seq_length": 2048})
        tracker.fail_experiment(exp_id, error_message="CUDA out of memory (OOM)")

    recs = tracker.generate_recommendations(recent_experiments=5)
    oom_rec = next((r for r in recs if "OOM" in r.get("description", "")), None)
    assert oom_rec is not None
    assert oom_rec["suggested_config"]["batch_size"] == 1


# ===================================================================
# 5. VISUAL ANALYTICS ENGINE
# ===================================================================


def test_visual_analytics_engine(tracker: ExperimentTracker):
    """Test Chart.js data generation."""
    exp_id = tracker.create_experiment(name="viz_run", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp_id, {"learning_rate": 2e-4, "lora_r": 16})

    for s in range(1, 6):
        tracker.log_metrics(
            experiment_id=exp_id,
            step=s * 10,
            train_loss=3.0 - (s * 0.4),
            eval_loss=3.1 - (s * 0.3),
            vram_allocated_gb=10.0 + s,
            tokens_per_second=1200.0,
            is_anomaly=(s == 3),
            anomaly_type="grad_explosion" if s == 3 else None,
        )

    tracker.complete_experiment(exp_id, final_train_loss=1.0, eval_pass_rate=0.9, eval_delta=0.1)

    viz = VisualAnalyticsEngine(tracker)

    # 1. Loss Curves
    loss_data = viz.generate_loss_curve_data([exp_id], smoothing_window=2)
    assert "labels" in loss_data
    assert len(loss_data["datasets"]) >= 1

    # 2. Quality Trend
    trend_data = viz.generate_quality_trend_data()
    assert "datasets" in trend_data
    assert len(trend_data["datasets"]) == 3

    # 3. Resource Utilization
    resource_data = viz.generate_resource_utilization_data(exp_id)
    assert "labels" in resource_data
    assert len(resource_data["datasets"]) == 3

    # 4. Anomaly Timeline
    anomalies = viz.generate_anomaly_timeline(exp_id)
    assert anomalies["total_anomalies"] == 1
    assert "grad_explosion" in anomalies["anomaly_types"]


# ===================================================================
# 6. TRAINING RUNNER INTEGRATION
# ===================================================================


def test_training_runner_tracks_experiments(tmp_path: Path):
    """Test TrainingRunner automatic lifecycle orchestration."""
    runner = TrainingRunner(tmp_path)
    exp_id = runner.run_training(
        {
            "name": "auto_tracked_run",
            "model_name": "Qwen/Qwen2.5-1.5B",
            "learning_rate": 2e-4,
            "batch_size": 2,
            "epochs": 1.0,
            "steps_data": [
                {"step": 10, "train_loss": 2.2, "eval_loss": 2.3},
                {"step": 20, "train_loss": 1.8, "eval_loss": 1.9},
            ],
            "final_train_loss": 1.8,
            "eval_pass_rate": 0.85,
            "eval_delta": 0.05,
        }
    )

    assert exp_id.startswith("exp_")
    exp = runner.tracker.get_experiment(exp_id)
    assert exp["status"] == "completed"
    assert exp["final_train_loss"] == 1.8

    metrics = runner.tracker.get_metrics(exp_id)
    assert len(metrics) == 2


# ===================================================================
# 7. CLI COMMANDS
# ===================================================================


def test_analytics_cli_commands(tmp_path: Path, monkeypatch):
    """Test moro analytics list, show, compare, trend, and recommend."""
    # Point require_project_root to tmp_path
    monkeypatch.setattr("moro.cli.analytics.require_project_root", lambda: tmp_path)

    tracker = ExperimentTracker(tmp_path / ".moro" / "analytics.db")
    exp1 = tracker.create_experiment(name="cli_run_1", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp1, {"learning_rate": 2e-4, "lora_r": 16})
    tracker.complete_experiment(exp1, final_train_loss=1.4, eval_delta=0.06, eval_pass_rate=0.82)

    exp2 = tracker.create_experiment(name="cli_run_2", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp2, {"learning_rate": 1e-4, "lora_r": 8})
    tracker.complete_experiment(exp2, final_train_loss=1.7, eval_delta=0.02, eval_pass_rate=0.75)

    # 1. List
    res = runner.invoke(analytics_app, ["list"])
    assert res.exit_code == 0
    assert "cli_run_1" in res.output

    # 2. Show
    res = runner.invoke(analytics_app, ["show", exp1])
    assert res.exit_code == 0
    assert exp1 in res.output

    # 3. Compare
    res = runner.invoke(analytics_app, ["compare", f"{exp1},{exp2}"])
    assert res.exit_code == 0
    assert "Comparing 2 experiments" in res.output

    # 4. Trend
    res = runner.invoke(analytics_app, ["trend"])
    assert res.exit_code == 0
    assert "Model Quality Trend" in res.output

    # 5. Recommend
    res = runner.invoke(analytics_app, ["recommend"])
    assert res.exit_code == 0
    assert "Experiment Recommendations" in res.output


# ===================================================================
# 8. MISSION CONTROL REST API ENDPOINTS
# ===================================================================


def test_mission_control_analytics_endpoints(tmp_path: Path, monkeypatch):
    """Test dashboard REST API endpoints for analytics."""
    monkeypatch.setattr("moro.dashboard.mission_control.get_project_root", lambda: tmp_path)

    tracker = ExperimentTracker(tmp_path / ".moro" / "analytics.db")
    exp1 = tracker.create_experiment(name="api_run_1", base_model="Qwen/Qwen2.5-1.5B")
    tracker.start_experiment(exp1, {"learning_rate": 2e-4, "lora_r": 16})
    tracker.log_metrics(exp1, step=10, train_loss=2.1, eval_loss=2.2)
    tracker.complete_experiment(exp1, final_train_loss=1.2, eval_delta=0.07, eval_pass_rate=0.86)

    client = TestClient(dashboard_app)

    # List experiments
    r = client.get("/api/analytics/experiments")
    assert r.status_code == 200
    assert len(r.json()["experiments"]) == 1

    # Detail
    r = client.get(f"/api/analytics/experiments/{exp1}")
    assert r.status_code == 200
    assert r.json()["experiment"]["experiment_id"] == exp1

    # Metrics
    r = client.get(f"/api/analytics/experiments/{exp1}/metrics")
    assert r.status_code == 200
    assert len(r.json()["metrics"]) == 1

    # Compare
    r = client.get(f"/api/analytics/compare?experiment_ids={exp1}")
    assert r.status_code == 200

    # Loss Curves Viz
    r = client.get(f"/api/analytics/viz/loss-curves?experiment_ids={exp1}")
    assert r.status_code == 200
    assert "datasets" in r.json()

    # Quality Trend Viz
    r = client.get("/api/analytics/viz/quality-trend")
    assert r.status_code == 200

    # Recommendations
    r = client.get("/api/analytics/recommendations")
    assert r.status_code == 200
    assert "recommendations" in r.json()
