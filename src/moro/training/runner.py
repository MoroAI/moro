"""SDK entry point for the canonical, artifact-producing training lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from moro.analytics.tracker import ExperimentTracker
from moro.config.loader import load_config
from moro.config.models import MoroConfig, TrainingConfig
from moro.core.errors import ConfigError


class TrainingResult(str):
    """Run ID with the recorded outcome available as a mapping."""

    def __new__(cls, run_id: str, data: dict[str, Any]):
        instance = super().__new__(cls, run_id)
        instance.run_id = run_id
        instance._data = data
        return instance

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


def training_config(root: Path, overrides: dict[str, Any]) -> MoroConfig:
    """Validate SDK recipe overrides without accepting supplied success metrics."""
    cfg = load_config(root / "moro.yaml")
    data = cfg.model_dump()
    mapping = {
        "model_name": ("model", "name"),
        "quantization": ("model", "quantization"),
        "lora_r": ("adapter", "r"),
        "lora_alpha": ("adapter", "alpha"),
        "lora_dropout": ("adapter", "dropout"),
        "target_modules": ("adapter", "target_modules"),
        "adapter_type": ("adapter", "type"),
        "seed": ("project", "seed"),
        "max_seq_length": ("dataset", "max_seq_length"),
    }
    metadata = {"name", "dataset_id", "target_model", "estimated_vram_gb"}
    for key, value in overrides.items():
        if key in TrainingConfig.model_fields:
            data["training"][key] = value
        elif key in mapping:
            section, field = mapping[key]
            data[section][field] = value
        elif key not in metadata:
            raise ConfigError(f"Unsupported training recipe field: {key}")
    if overrides.get("target_model") and not overrides.get("model_name"):
        data["model"]["name"] = overrides["target_model"]
    return MoroConfig.model_validate(data)


class TrainingRunner:
    def __init__(self, project_root: Path, experiment_tracker: Any = None):
        self.project_root = Path(project_root).resolve()
        self.tracker = experiment_tracker or ExperimentTracker(
            self.project_root / ".moro" / "analytics.db"
        )

    def run_training(self, config=None, recipe=None, dataset_id=None, progress_callback=None):
        from moro.cli.train import execute_training

        overrides = dict(config or recipe or {})
        cfg = training_config(self.project_root, overrides)
        if progress_callback:
            progress_callback("Validating dataset and starting training", None)
        result = execute_training(
            self.project_root,
            cfg,
            run_name=overrides.get("name"),
            dataset_id=dataset_id or overrides.get("dataset_id"),
        )
        if progress_callback:
            progress_callback("Training completed", 100.0)
        return TrainingResult(result["run_id"], result)

    async def run_training_async(self, experiment_id, dataset_id, recipe, progress_callback=None):
        from moro.training.async_runner import AsyncTrainingRunner

        return await AsyncTrainingRunner(self.project_root, self.tracker).run_training_async(
            experiment_id, dataset_id, recipe, progress_callback
        )
