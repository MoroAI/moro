"""
MoroAI Experiment Tracker.

Core engine for tracking experiments, collecting metrics,
and providing analytics.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moro.analytics.schema import get_experiment_db, initialize_experiment_db


class ExperimentTracker:
    """Central experiment tracking engine.

    Provides:
    - Experiment lifecycle management
    - Metric collection and storage
    - Hyperparameter snapshotting
    - Run comparison and analysis
    - Recommendation generation
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        if not db_path.exists():
            initialize_experiment_db(db_path)

    def _get_conn(self):
        return get_experiment_db(self.db_path)

    def _generate_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    # ===================================================================
    # EXPERIMENT LIFECYCLE
    # ===================================================================

    def create_experiment(
        self,
        name: str,
        base_model: str,
        dataset_id: str | None = None,
        dataset_name: str | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
        parent_experiment_id: str | None = None,
        state_node_id: str | None = None,
    ) -> str:
        """Create a new experiment and return its ID."""
        experiment_id = self._generate_id("exp")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO experiments (
                    experiment_id, experiment_name, status,
                    base_model, dataset_id, dataset_name,
                    tags_json, notes, parent_experiment_id,
                    state_node_id, created_at
                ) VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment_id,
                    name,
                    base_model,
                    dataset_id,
                    dataset_name,
                    json.dumps(tags or []),
                    notes,
                    parent_experiment_id,
                    state_node_id,
                    now,
                ),
            )
            conn.commit()
            return experiment_id
        finally:
            conn.close()

    def start_experiment(
        self,
        experiment_id: str,
        hyperparameters: dict[str, Any],
        gpu_name: str | None = None,
        gpu_vram_gb: float | None = None,
    ) -> None:
        """Mark an experiment as started and record hyperparameters."""
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                UPDATE experiments
                SET status = 'running', started_at = ?,
                    gpu_name = ?, gpu_vram_gb = ?
                WHERE experiment_id = ?
                """,
                (now, gpu_name, gpu_vram_gb, experiment_id),
            )

            param_id = self._generate_id("param")
            conn.execute(
                """
                INSERT INTO hyperparameters (
                    param_id, experiment_id,
                    learning_rate, batch_size, gradient_accumulation_steps,
                    epochs, warmup_ratio, weight_decay,
                    lora_r, lora_alpha, lora_dropout, target_modules_json,
                    optimizer, scheduler, max_seq_length, gradient_checkpointing,
                    kl_penalty_beta, replay_ratio, seed, fp16, bf16,
                    full_config_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    param_id,
                    experiment_id,
                    hyperparameters.get("learning_rate"),
                    hyperparameters.get("batch_size"),
                    hyperparameters.get("gradient_accumulation_steps"),
                    hyperparameters.get("epochs"),
                    hyperparameters.get("warmup_ratio"),
                    hyperparameters.get("weight_decay"),
                    hyperparameters.get("lora_r"),
                    hyperparameters.get("lora_alpha"),
                    hyperparameters.get("lora_dropout"),
                    json.dumps(hyperparameters.get("target_modules", [])),
                    hyperparameters.get("optimizer"),
                    hyperparameters.get("scheduler"),
                    hyperparameters.get("max_seq_length"),
                    int(bool(hyperparameters.get("gradient_checkpointing", 0))),
                    hyperparameters.get("kl_penalty_beta"),
                    hyperparameters.get("replay_ratio"),
                    hyperparameters.get("seed"),
                    int(bool(hyperparameters.get("fp16", 0))),
                    int(bool(hyperparameters.get("bf16", 0))),
                    json.dumps(hyperparameters),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def log_metrics(
        self,
        experiment_id: str,
        step: int,
        epoch: float | None = None,
        train_loss: float | None = None,
        eval_loss: float | None = None,
        grad_norm: float | None = None,
        learning_rate: float | None = None,
        vram_allocated_gb: float | None = None,
        tokens_per_second: float | None = None,
        is_anomaly: bool = False,
        anomaly_type: str | None = None,
    ) -> None:
        """Log metrics for a single training step."""
        metric_id = self._generate_id("metric")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                INSERT INTO metrics (
                    metric_id, experiment_id, step, epoch, timestamp,
                    train_loss, eval_loss, grad_norm, learning_rate,
                    vram_allocated_gb, tokens_per_second,
                    is_anomaly, anomaly_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metric_id,
                    experiment_id,
                    step,
                    epoch,
                    now,
                    train_loss,
                    eval_loss,
                    grad_norm,
                    learning_rate,
                    vram_allocated_gb,
                    tokens_per_second,
                    int(is_anomaly),
                    anomaly_type,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_experiment(
        self,
        experiment_id: str,
        final_train_loss: float | None = None,
        final_eval_loss: float | None = None,
        eval_pass_rate: float | None = None,
        eval_delta: float | None = None,
        peak_vram_gb: float | None = None,
        total_steps: int | None = None,
        tokens_per_second: float | None = None,
    ) -> None:
        """Mark an experiment as completed."""
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT started_at FROM experiments WHERE experiment_id = ?",
                [experiment_id],
            ).fetchone()

            duration = None
            if row and row["started_at"]:
                start = datetime.fromisoformat(row["started_at"])
                duration = (datetime.now(timezone.utc) - start).total_seconds()

            conn.execute(
                """
                UPDATE experiments
                SET status = 'completed', completed_at = ?, duration_seconds = ?,
                    final_train_loss = ?, final_eval_loss = ?,
                    eval_pass_rate = ?, eval_delta = ?,
                    peak_vram_gb = ?, total_steps = ?, tokens_per_second = ?
                WHERE experiment_id = ?
                """,
                (
                    now,
                    duration,
                    final_train_loss,
                    final_eval_loss,
                    eval_pass_rate,
                    eval_delta,
                    peak_vram_gb,
                    total_steps,
                    tokens_per_second,
                    experiment_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def fail_experiment(
        self,
        experiment_id: str,
        error_message: str | None = None,
    ) -> None:
        """Mark an experiment as failed."""
        now = datetime.now(timezone.utc).isoformat()

        conn = self._get_conn()
        try:
            conn.execute(
                """
                UPDATE experiments
                SET status = 'failed', completed_at = ?, notes = ?
                WHERE experiment_id = ?
                """,
                (now, error_message, experiment_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ===================================================================
    # QUERY AND ANALYSIS
    # ===================================================================

    def get_experiment(self, experiment_id: str) -> dict[str, Any] | None:
        """Get a single experiment by ID or prefix."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM experiments
                WHERE experiment_id = ? OR experiment_id LIKE ? || '%'
                ORDER BY created_at DESC LIMIT 1
                """,
                (experiment_id, experiment_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_experiments(
        self,
        status: str | None = None,
        base_model: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List experiments with optional filters."""
        conn = self._get_conn()
        try:
            conditions = []
            params: list[Any] = []

            if status:
                conditions.append("status = ?")
                params.append(status)

            if base_model:
                conditions.append("base_model LIKE ?")
                params.append(f"%{base_model}%")

            where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            rows = conn.execute(
                f"""
                SELECT * FROM experiments
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset],
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_metrics(
        self,
        experiment_id: str,
        metric_name: str | None = None,
        start_step: int | None = None,
        end_step: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get time-series metrics for an experiment."""
        conn = self._get_conn()
        try:
            conditions = ["(experiment_id = ? OR experiment_id LIKE ? || '%')"]
            params: list[Any] = [experiment_id, experiment_id]

            if start_step is not None:
                conditions.append("step >= ?")
                params.append(start_step)

            if end_step is not None:
                conditions.append("step <= ?")
                params.append(end_step)

            where_clause = f"WHERE {' AND '.join(conditions)}"

            rows = conn.execute(
                f"""
                SELECT * FROM metrics
                {where_clause}
                ORDER BY step ASC
                """,
                params,
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_hyperparameters(self, experiment_id: str) -> dict[str, Any] | None:
        """Get hyperparameters for an experiment."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                """
                SELECT * FROM hyperparameters
                WHERE experiment_id = ? OR experiment_id LIKE ? || '%'
                LIMIT 1
                """,
                (experiment_id, experiment_id),
            ).fetchone()

            if row:
                result = dict(row)
                try:
                    result["target_modules"] = json.loads(result.get("target_modules_json") or "[]")
                except Exception:
                    result["target_modules"] = []
                try:
                    result["full_config"] = json.loads(result.get("full_config_json") or "{}")
                except Exception:
                    result["full_config"] = {}
                return result
            return None
        finally:
            conn.close()

    def compare_experiments(
        self,
        experiment_ids: list[str],
    ) -> dict[str, Any]:
        """Compare multiple experiments side-by-side."""
        experiments = []
        hyperparams = []

        for exp_id in experiment_ids:
            exp = self.get_experiment(exp_id)
            if exp:
                experiments.append(exp)
                full_id = exp["experiment_id"]
                hp = self.get_hyperparameters(full_id)
                if hp:
                    hyperparams.append(hp)

        if not experiments:
            return {"error": "No experiments found"}

        hp_diffs = self._find_hyperparameter_differences(hyperparams)

        metrics_comparison = {
            "experiment_ids": [e["experiment_id"] for e in experiments],
            "final_train_loss": [e.get("final_train_loss") for e in experiments],
            "final_eval_loss": [e.get("final_eval_loss") for e in experiments],
            "eval_pass_rate": [e.get("eval_pass_rate") for e in experiments],
            "eval_delta": [e.get("eval_delta") for e in experiments],
            "duration_seconds": [e.get("duration_seconds") for e in experiments],
            "peak_vram_gb": [e.get("peak_vram_gb") for e in experiments],
        }

        best_idx = self._determine_best_experiment(experiments)

        return {
            "experiments": experiments,
            "hyperparameters": hyperparams,
            "hyperparameter_differences": hp_diffs,
            "metrics_comparison": metrics_comparison,
            "best_experiment_id": experiments[best_idx]["experiment_id"] if best_idx is not None else None,
            "best_experiment_index": best_idx,
        }

    def _find_hyperparameter_differences(
        self,
        hyperparams: list[dict[str, Any]],
    ) -> dict[str, list[Any]]:
        """Find which hyperparameters differ between experiments."""
        if len(hyperparams) < 2:
            return {}

        compare_keys = [
            "learning_rate",
            "batch_size",
            "gradient_accumulation_steps",
            "epochs",
            "warmup_ratio",
            "weight_decay",
            "lora_r",
            "lora_alpha",
            "lora_dropout",
            "optimizer",
            "max_seq_length",
            "gradient_checkpointing",
        ]

        diffs: dict[str, list[Any]] = {}
        for key in compare_keys:
            values = [hp.get(key) for hp in hyperparams]
            if len({str(v) for v in values}) > 1:
                diffs[key] = values

        return diffs

    def _determine_best_experiment(self, experiments: list[dict[str, Any]]) -> int | None:
        """Determine which experiment is 'best' based on multi-objective scoring."""
        if not experiments:
            return None

        scores = []
        for exp in experiments:
            score = 0.0

            eval_delta = exp.get("eval_delta") or 0.0
            score += 0.4 * min(1.0, max(0.0, eval_delta / 0.5))

            pass_rate = exp.get("eval_pass_rate") or 0.0
            score += 0.3 * pass_rate

            train_loss = exp.get("final_train_loss") or 5.0
            score += 0.15 * max(0.0, 1.0 - (train_loss / 5.0))

            duration = exp.get("duration_seconds") or 3600.0
            score += 0.10 * max(0.0, 1.0 - (duration / 3600.0))

            vram = exp.get("peak_vram_gb") or 24.0
            score += 0.05 * max(0.0, 1.0 - (vram / 24.0))

            scores.append(score)

        return scores.index(max(scores)) if scores else None

    # ===================================================================
    # ANALYTICS AND INSIGHTS
    # ===================================================================

    def get_quality_trend(
        self,
        base_model: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get the trend of model quality over time."""
        conn = self._get_conn()
        try:
            conditions = ["status = 'completed'"]
            params: list[Any] = []

            if base_model:
                conditions.append("base_model LIKE ?")
                params.append(f"%{base_model}%")

            where_clause = f"WHERE {' AND '.join(conditions)}"

            rows = conn.execute(
                f"""
                SELECT experiment_id, experiment_name, created_at,
                       eval_pass_rate, eval_delta, final_train_loss,
                       duration_seconds, peak_vram_gb
                FROM experiments
                {where_clause}
                ORDER BY created_at ASC
                LIMIT ?
                """,
                params + [limit],
            ).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_hyperparameter_correlations(
        self,
        metric_name: str = "eval_delta",
        limit: int = 100,
    ) -> dict[str, Any]:
        """Analyze correlations between hyperparameters and a target metric."""
        conn = self._get_conn()
        try:
            rows = conn.execute(
                f"""
                SELECT e.experiment_id, e.{metric_name} as target_metric,
                       h.learning_rate, h.batch_size, h.lora_r, h.lora_alpha,
                       h.epochs, h.warmup_ratio, h.max_seq_length
                FROM experiments e
                JOIN hyperparameters h ON e.experiment_id = h.experiment_id
                WHERE e.{metric_name} IS NOT NULL
                ORDER BY e.created_at DESC
                LIMIT ?
                """,
                [limit],
            ).fetchall()

            if len(rows) < 3:
                return {"error": "Not enough data for correlation analysis", "count": len(rows)}

            target_values = [float(row["target_metric"]) for row in rows if row["target_metric"] is not None]

            correlations: dict[str, float | None] = {}
            hp_keys = [
                "learning_rate",
                "batch_size",
                "lora_r",
                "lora_alpha",
                "epochs",
                "warmup_ratio",
                "max_seq_length",
            ]

            for key in hp_keys:
                hp_values = [float(row[key]) for row in rows if row[key] is not None]
                if len(hp_values) < 3:
                    continue
                try:
                    c = self._pearson_correlation(
                        hp_values[: len(target_values)],
                        target_values[: len(hp_values)],
                    )
                    correlations[key] = round(c, 4)
                except Exception:
                    correlations[key] = None

            valid_corrs = {k: v for k, v in correlations.items() if v is not None}
            strongest_pos = max(valid_corrs.items(), key=lambda x: x[1])[0] if valid_corrs else None
            strongest_neg = min(valid_corrs.items(), key=lambda x: x[1])[0] if valid_corrs else None

            return {
                "metric_name": metric_name,
                "sample_size": len(rows),
                "correlations": correlations,
                "strongest_positive": strongest_pos,
                "strongest_negative": strongest_neg,
            }
        finally:
            conn.close()

    def _pearson_correlation(self, x: list[float], y: list[float]) -> float:
        """Calculate Pearson correlation coefficient."""
        n = min(len(x), len(y))
        if n < 2:
            return 0.0

        x = x[:n]
        y = y[:n]
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
        var_x = sum((xi - mean_x) ** 2 for xi in x)
        var_y = sum((yi - mean_y) ** 2 for yi in y)
        denominator = (var_x * var_y) ** 0.5

        if denominator == 0:
            return 0.0
        return numerator / denominator

    def generate_recommendations(
        self,
        recent_experiments: int = 10,
    ) -> list[dict[str, Any]]:
        """Generate recommendations for the next experiment based on history."""
        experiments = self.list_experiments(limit=recent_experiments)
        if not experiments:
            return [
                {
                    "rec_id": self._generate_id("rec"),
                    "rec_type": "start_training",
                    "description": "No experiments found. Start your first training run with moro train.",
                    "confidence": 1.0,
                }
            ]

        recommendations: list[dict[str, Any]] = []

        lr_rec = self._analyze_learning_rate_effectiveness(experiments)
        if lr_rec:
            recommendations.append(lr_rec)

        lora_rec = self._analyze_lora_rank_effectiveness(experiments)
        if lora_rec:
            recommendations.append(lora_rec)

        diminishing = self._check_diminishing_returns(experiments)
        if diminishing:
            recommendations.append(diminishing)

        recommendations.extend(self._detect_failure_patterns(experiments))
        return recommendations

    def _analyze_learning_rate_effectiveness(self, experiments: list[dict[str, Any]]) -> dict[str, Any] | None:
        lr_groups: dict[float, list[dict[str, Any]]] = {}
        for exp in experiments:
            hp = self.get_hyperparameters(exp["experiment_id"])
            if hp and hp.get("learning_rate"):
                lr = float(hp["learning_rate"])
                lr_groups.setdefault(lr, []).append(exp)

        if len(lr_groups) < 2:
            return None

        best_lr = None
        best_delta = -999.0
        for lr, exps in lr_groups.items():
            avg_delta = sum(e.get("eval_delta") or 0.0 for e in exps) / len(exps)
            if avg_delta > best_delta:
                best_delta = avg_delta
                best_lr = lr

        if best_lr:
            return {
                "rec_id": self._generate_id("rec"),
                "rec_type": "hyperparameter_change",
                "description": f"Learning rate {best_lr} produced the best results (avg delta: {best_delta:+.3f}).",
                "suggested_config": {"learning_rate": best_lr},
                "confidence": 0.75,
                "reasoning": f"Analyzed across {len(lr_groups)} learning rate variants.",
            }
        return None

    def _analyze_lora_rank_effectiveness(self, experiments: list[dict[str, Any]]) -> dict[str, Any] | None:
        rank_groups: dict[int, list[dict[str, Any]]] = {}
        for exp in experiments:
            hp = self.get_hyperparameters(exp["experiment_id"])
            if hp and hp.get("lora_r"):
                r = int(hp["lora_r"])
                rank_groups.setdefault(r, []).append(exp)

        if len(rank_groups) < 2:
            return None

        best_r = None
        best_delta = -999.0
        for r, exps in rank_groups.items():
            avg_delta = sum(e.get("eval_delta") or 0.0 for e in exps) / len(exps)
            if avg_delta > best_delta:
                best_delta = avg_delta
                best_r = r

        if best_r:
            return {
                "rec_id": self._generate_id("rec"),
                "rec_type": "hyperparameter_change",
                "description": f"LoRA rank r={best_r} produced the highest average evaluation delta ({best_delta:+.3f}).",
                "suggested_config": {"lora_r": best_r, "lora_alpha": best_r * 2},
                "confidence": 0.70,
                "reasoning": f"Analyzed across {len(rank_groups)} LoRA rank variations.",
            }
        return None

    def _check_diminishing_returns(self, experiments: list[dict[str, Any]]) -> dict[str, Any] | None:
        completed = [e for e in experiments if e.get("status") == "completed"]
        if len(completed) < 3:
            return None

        completed.sort(key=lambda x: x.get("created_at", ""))
        deltas = [e.get("eval_delta") or 0.0 for e in completed[-5:]]
        if len(deltas) >= 3 and (deltas[-1] < deltas[-2] < deltas[-3]):
            return {
                "rec_id": self._generate_id("rec"),
                "rec_type": "stop_training",
                "description": "Evaluation deltas are showing diminishing returns. Prioritize data quality pruning before retraining.",
                "confidence": 0.65,
                "reasoning": f"Recent 3 eval deltas: {deltas[-3]:+.3f}, {deltas[-2]:+.3f}, {deltas[-1]:+.3f}",
            }
        return None

    def _detect_failure_patterns(self, experiments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        patterns = []
        failed = [e for e in experiments if e.get("status") == "failed"]
        if len(failed) >= 2:
            notes = [str(e.get("notes") or "") for e in failed]
            oom_count = sum(1 for n in notes if "OOM" in n or "out of memory" in n.lower())
            if oom_count >= 2:
                patterns.append(
                    {
                        "rec_id": self._generate_id("rec"),
                        "rec_type": "hyperparameter_change",
                        "description": f"Repeated OOM failures detected ({oom_count}). Consider reducing batch size or gradient checkpointing.",
                        "suggested_config": {"batch_size": 1, "gradient_checkpointing": 1},
                        "confidence": 0.85,
                        "reasoning": "Out-of-memory pattern detected across multiple training attempts.",
                    }
                )
        return patterns
