"""
MoroAI Visual Analytics Engine.

Generates data structures for frontend visualization components:
loss curves, hyperparameter heatmaps, output comparisons, quality trends,
resource timelines, and anomaly distributions.
"""

from __future__ import annotations

from typing import Any

from moro.analytics.tracker import ExperimentTracker


class VisualAnalyticsEngine:
    """Generates visualization data for the Mission Control Dashboard."""

    def __init__(self, tracker: ExperimentTracker) -> None:
        self.tracker = tracker

    # ===================================================================
    # LOSS CURVE VISUALIZATION
    # ===================================================================

    def generate_loss_curve_data(
        self,
        experiment_ids: list[str],
        include_eval: bool = True,
        smoothing_window: int = 10,
    ) -> dict[str, Any]:
        """Generate data for overlaid loss curves compatible with Chart.js."""
        colors = [
            "#3b82f6",
            "#ef4444",
            "#22c55e",
            "#f59e0b",
            "#8b5cf6",
            "#06b6d4",
            "#ec4899",
            "#84cc16",
            "#f97316",
            "#6366f1",
        ]

        datasets: list[dict[str, Any]] = []
        all_steps: set[int] = set()

        for idx, exp_id in enumerate(experiment_ids):
            color = colors[idx % len(colors)]
            metrics = self.tracker.get_metrics(exp_id)
            if not metrics:
                continue

            steps = [int(m["step"]) for m in metrics]
            all_steps.update(steps)

            train_losses = [m.get("train_loss") for m in metrics]
            if smoothing_window > 1:
                train_losses = self._smooth_data(train_losses, smoothing_window)

            datasets.append(
                {
                    "label": f"{exp_id}_train",
                    "data": train_losses,
                    "borderColor": color,
                    "backgroundColor": color,
                    "borderDash": [],
                    "tension": 0.2,
                }
            )

            if include_eval:
                eval_losses = [m.get("eval_loss") for m in metrics]
                if any(v is not None for v in eval_losses):
                    if smoothing_window > 1:
                        eval_losses = self._smooth_data(eval_losses, smoothing_window)
                    datasets.append(
                        {
                            "label": f"{exp_id}_eval",
                            "data": eval_losses,
                            "borderColor": color,
                            "backgroundColor": color,
                            "borderDash": [5, 5],
                            "tension": 0.2,
                        }
                    )

        return {
            "labels": sorted(list(all_steps)),
            "datasets": datasets,
            "title": "Training & Validation Loss Curves",
            "x_axis": "Step",
            "y_axis": "Loss",
        }

    def _smooth_data(self, data: list[float | None], window: int) -> list[float | None]:
        """Apply moving average smoothing."""
        if not data or window <= 1:
            return data

        smoothed: list[float | None] = []
        for i in range(len(data)):
            start = max(0, i - window // 2)
            end = min(len(data), i + window // 2 + 1)
            window_data = [v for v in data[start:end] if v is not None]
            if window_data:
                smoothed.append(round(sum(window_data) / len(window_data), 4))
            else:
                smoothed.append(None)
        return smoothed

    # ===================================================================
    # HYPERPARAMETER HEATMAP
    # ===================================================================

    def generate_hyperparameter_heatmap(
        self,
        x_param: str = "learning_rate",
        y_param: str = "lora_r",
        metric: str = "eval_delta",
    ) -> dict[str, Any]:
        """Generate data for a 2D hyperparameter heatmap."""
        conn = self.tracker._get_conn()
        try:
            rows = conn.execute(
                f"""
                SELECT h.{x_param} as x_val, h.{y_param} as y_val, e.{metric} as metric_val
                FROM experiments e
                JOIN hyperparameters h ON e.experiment_id = h.experiment_id
                WHERE e.{metric} IS NOT NULL
                  AND h.{x_param} IS NOT NULL
                  AND h.{y_param} IS NOT NULL
                """
            ).fetchall()

            if not rows:
                return {"error": "No data available for heatmap"}

            x_values = sorted(list({row["x_val"] for row in rows}))
            y_values = sorted(list({row["y_val"] for row in rows}))

            matrix: list[list[float | None]] = [[None for _ in x_values] for _ in y_values]

            for row in rows:
                x_idx = x_values.index(row["x_val"])
                y_idx = y_values.index(row["y_val"])
                matrix[y_idx][x_idx] = row["metric_val"]

            return {
                "x_values": x_values,
                "y_values": y_values,
                "matrix": matrix,
                "x_label": x_param,
                "y_label": y_param,
                "metric": metric,
                "title": f"{metric} vs {x_param} and {y_param}",
            }
        finally:
            conn.close()

    # ===================================================================
    # MODEL OUTPUT COMPARISON
    # ===================================================================

    def generate_output_comparison(
        self,
        experiment_ids: list[str],
        prompt_category: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Generate side-by-side model output comparison data."""
        conn = self.tracker._get_conn()
        try:
            if len(experiment_ids) == 1:
                prompts = conn.execute(
                    """
                    SELECT DISTINCT prompt, prompt_category
                    FROM model_outputs
                    WHERE experiment_id = ?
                    LIMIT ?
                    """,
                    [experiment_ids[0], limit],
                ).fetchall()
            else:
                placeholders = ",".join(["?" for _ in experiment_ids])
                prompts = conn.execute(
                    f"""
                    SELECT prompt, prompt_category, COUNT(DISTINCT experiment_id) as exp_count
                    FROM model_outputs
                    WHERE experiment_id IN ({placeholders})
                    GROUP BY prompt
                    HAVING exp_count > 1
                    LIMIT ?
                    """,
                    experiment_ids + [limit],
                ).fetchall()

            comparisons = []
            for prompt_row in prompts:
                prompt = prompt_row["prompt"]
                outputs: dict[str, Any] = {}
                for exp_id in experiment_ids:
                    row = conn.execute(
                        """
                        SELECT completion, eval_score, eval_passed, latency_ms
                        FROM model_outputs
                        WHERE experiment_id = ? AND prompt = ?
                        LIMIT 1
                        """,
                        [exp_id, prompt],
                    ).fetchone()
                    if row:
                        outputs[exp_id] = {
                            "completion": row["completion"],
                            "eval_score": row["eval_score"],
                            "eval_passed": bool(row["eval_passed"]),
                            "latency_ms": row["latency_ms"],
                        }

                if outputs:
                    comparisons.append(
                        {
                            "prompt": prompt,
                            "category": prompt_row["prompt_category"],
                            "outputs": outputs,
                        }
                    )

            return {
                "experiment_ids": experiment_ids,
                "comparisons": comparisons,
                "total_comparisons": len(comparisons),
            }
        finally:
            conn.close()

    # ===================================================================
    # QUALITY TREND VISUALIZATION
    # ===================================================================

    def generate_quality_trend_data(
        self,
        base_model: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Generate data for model quality trend over time."""
        trend_data = self.tracker.get_quality_trend(base_model, limit)
        if not trend_data:
            return {"error": "No completed experiments found"}

        return {
            "labels": [e["created_at"][:10] for e in trend_data],
            "datasets": [
                {
                    "label": "Eval Pass Rate",
                    "data": [e.get("eval_pass_rate") for e in trend_data],
                    "borderColor": "#22c55e",
                    "backgroundColor": "#22c55e",
                    "yAxisID": "pass_rate",
                },
                {
                    "label": "Eval Delta",
                    "data": [e.get("eval_delta") for e in trend_data],
                    "borderColor": "#3b82f6",
                    "backgroundColor": "#3b82f6",
                    "yAxisID": "delta",
                },
                {
                    "label": "Training Loss",
                    "data": [e.get("final_train_loss") for e in trend_data],
                    "borderColor": "#ef4444",
                    "backgroundColor": "#ef4444",
                    "yAxisID": "loss",
                },
            ],
            "experiment_names": [e["experiment_name"] for e in trend_data],
            "title": "Model Quality Trend",
        }

    # ===================================================================
    # RESOURCE UTILIZATION VISUALIZATION
    # ===================================================================

    def generate_resource_utilization_data(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Generate data for resource utilization over time."""
        metrics = self.tracker.get_metrics(experiment_id)
        if not metrics:
            return {"error": "No metrics found for experiment"}

        return {
            "labels": [m["step"] for m in metrics],
            "datasets": [
                {
                    "label": "VRAM Allocated (GB)",
                    "data": [m.get("vram_allocated_gb") for m in metrics],
                    "borderColor": "#8b5cf6",
                    "backgroundColor": "#8b5cf6",
                    "yAxisID": "vram",
                },
                {
                    "label": "Tokens/sec",
                    "data": [m.get("tokens_per_second") for m in metrics],
                    "borderColor": "#06b6d4",
                    "backgroundColor": "#06b6d4",
                    "yAxisID": "throughput",
                },
                {
                    "label": "Grad Norm",
                    "data": [m.get("grad_norm") for m in metrics],
                    "borderColor": "#f59e0b",
                    "backgroundColor": "#f59e0b",
                    "yAxisID": "grad",
                },
            ],
            "title": f"Resource Utilization: {experiment_id}",
        }

    # ===================================================================
    # ANOMALY DETECTION VISUALIZATION
    # ===================================================================

    def generate_anomaly_timeline(
        self,
        experiment_id: str,
    ) -> dict[str, Any]:
        """Generate data for anomaly timeline visualization."""
        conn = self.tracker._get_conn()
        try:
            rows = conn.execute(
                """
                SELECT step, train_loss, is_anomaly, anomaly_type
                FROM metrics
                WHERE experiment_id = ? AND is_anomaly = 1
                ORDER BY step ASC
                """,
                [experiment_id],
            ).fetchall()

            anomalies = [dict(row) for row in rows]
            types = list({a["anomaly_type"] for a in anomalies if a["anomaly_type"]})

            return {
                "experiment_id": experiment_id,
                "anomalies": anomalies,
                "total_anomalies": len(anomalies),
                "anomaly_types": types,
            }
        finally:
            conn.close()
