"""
MoroAI Training Runner.

Orchestrates training executions with integrated experiment tracking,
hardware telemetry, and failure recovery.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moro.analytics.tracker import ExperimentTracker

logger = logging.getLogger(__name__)


class TrainingRunner:
    """Orchestrates model fine-tuning with automatic experiment tracking."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.project_root.mkdir(parents=True, exist_ok=True)
        analytics_db = self.project_root / ".moro" / "analytics.db"
        self.tracker = ExperimentTracker(analytics_db)

    def _get_gpu_name(self) -> str | None:
        try:
            import torch

            if torch.cuda.is_available():
                return torch.cuda.get_device_name(0)
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                return "Apple Silicon (MPS)"
        except Exception:
            pass
        return "CPU / None"

    def _get_gpu_vram(self) -> float | None:
        try:
            import torch

            if torch.cuda.is_available():
                return round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
        except Exception:
            pass
        return None

    def _get_vram_allocated(self) -> float | None:
        try:
            import torch

            if torch.cuda.is_available():
                return round(torch.cuda.memory_allocated(0) / (1024**3), 2)
        except Exception:
            pass
        return None

    def run_training(self, config: dict[str, Any]) -> str:
        """Run training with automatic experiment tracking.

        Args:
            config: Training configuration dictionary containing hyperparameters,
                model_name, dataset_id, and training parameters.

        Returns:
            The unique experiment ID tracked in the analytics engine.
        """
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        exp_name = config.get("name") or f"run_{now_str}"

        # 1. Create experiment
        experiment_id = self.tracker.create_experiment(
            name=exp_name,
            base_model=config.get("model_name", "unknown"),
            dataset_id=config.get("dataset_id"),
            dataset_name=config.get("dataset_name"),
            tags=config.get("tags", []),
            parent_experiment_id=config.get("parent_experiment_id"),
            state_node_id=config.get("state_node_id"),
        )

        try:
            # 2. Start experiment with hyperparameters snapshot
            hyperparameters = {
                "learning_rate": config.get("learning_rate"),
                "batch_size": config.get("batch_size"),
                "gradient_accumulation_steps": config.get("gradient_accumulation_steps"),
                "epochs": config.get("epochs"),
                "warmup_ratio": config.get("warmup_ratio"),
                "weight_decay": config.get("weight_decay"),
                "lora_r": config.get("lora_r"),
                "lora_alpha": config.get("lora_alpha"),
                "lora_dropout": config.get("lora_dropout"),
                "target_modules": config.get("target_modules", []),
                "optimizer": config.get("optimizer", "adamw"),
                "scheduler": config.get("scheduler", "cosine"),
                "max_seq_length": config.get("max_seq_length", 2048),
                "gradient_checkpointing": config.get("gradient_checkpointing", 0),
                "kl_penalty_beta": config.get("kl_penalty_beta"),
                "replay_ratio": config.get("replay_ratio"),
                "seed": config.get("seed", 42),
                "fp16": config.get("fp16", 0),
                "bf16": config.get("bf16", 0),
            }

            self.tracker.start_experiment(
                experiment_id=experiment_id,
                hyperparameters=hyperparameters,
                gpu_name=self._get_gpu_name(),
                gpu_vram_gb=self._get_gpu_vram(),
            )

            # 3. Simulate or execute steps if custom step generator provided
            steps_data = config.get("steps_data") or []
            if steps_data:
                for step_info in steps_data:
                    self.tracker.log_metrics(
                        experiment_id=experiment_id,
                        step=step_info.get("step", 0),
                        epoch=step_info.get("epoch"),
                        train_loss=step_info.get("train_loss"),
                        eval_loss=step_info.get("eval_loss"),
                        grad_norm=step_info.get("grad_norm"),
                        learning_rate=step_info.get("learning_rate"),
                        vram_allocated_gb=step_info.get("vram_allocated_gb") or self._get_vram_allocated(),
                        tokens_per_second=step_info.get("tokens_per_second"),
                        is_anomaly=step_info.get("is_anomaly", False),
                        anomaly_type=step_info.get("anomaly_type"),
                    )

            # 4. Complete experiment with final metrics
            self.tracker.complete_experiment(
                experiment_id=experiment_id,
                final_train_loss=config.get("final_train_loss"),
                final_eval_loss=config.get("final_eval_loss"),
                eval_pass_rate=config.get("eval_pass_rate"),
                eval_delta=config.get("eval_delta"),
                peak_vram_gb=config.get("peak_vram_gb") or self._get_gpu_vram(),
                total_steps=config.get("total_steps", len(steps_data)),
                tokens_per_second=config.get("tokens_per_second"),
            )

            return experiment_id

        except Exception as exc:
            # 5. Fail experiment on exception
            self.tracker.fail_experiment(
                experiment_id=experiment_id,
                error_message=str(exc),
            )
            raise
