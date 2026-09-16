"""
Abstract training backend protocol.
All concrete backends must implement this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from moro.config.models import MoroConfig


class TrainingBackend(ABC):
    """Abstract base for training backends."""

    @abstractmethod
    def validate(self, config: MoroConfig, dataset_path: Path) -> list[str]:
        """
        Validate that the config and dataset are ready for training.
        Returns a (possibly empty) list of warning messages.
        Raises TrainingError on fatal validation failures.
        """
        ...

    @abstractmethod
    def estimate_memory(self, config: MoroConfig) -> float:
        """
        Estimate peak VRAM usage in GB for the given config.
        Returns 0.0 if estimation is not possible.
        """
        ...

    @abstractmethod
    def train(
        self,
        config: MoroConfig,
        dataset_path: Path,
        output_dir: Path,
        run_id: str,
        dry_run: bool = False,
    ) -> dict:
        """
        Execute training.

        Args:
            config: Validated MoroConfig.
            dataset_path: Path to train.jsonl split.
            output_dir: Directory to save adapter/checkpoints.
            run_id: Run identifier for logging.
            dry_run: If True, validate and estimate without actually training.

        Returns:
            Dict with keys: train_loss, validation_loss, peak_vram_gb, tokens_per_sec.
        """
        ...
