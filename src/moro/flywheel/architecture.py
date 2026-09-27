"""
Abstract interfaces for the MoroAI DPO Continuous Learning Flywheel.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from moro.flywheel.models import InferenceLogPayload, PreferencePair


class AbstractLogIngestor(ABC):
    """Abstract interface for ingesting production inference logs."""

    @abstractmethod
    def ingest_logs(self, source_path: Path | None = None) -> list[InferenceLogPayload]:
        """Ingest unprocessed logs."""
        ...

    @abstractmethod
    def mark_processed(
        self,
        session_ids: list[str],
        epoch_id: str,
        log_ids: list[str] | None = None,
    ) -> int:
        """Mark logs as processed for idempotency."""
        ...

    @abstractmethod
    def get_pending_count(self) -> int:
        """Count unprocessed logs."""
        ...


class AbstractPreferenceExtractor(ABC):
    """Abstract interface for converting inference logs into preference pairs."""

    @abstractmethod
    def extract_pairs(self, logs: list[InferenceLogPayload]) -> list[PreferencePair]:
        """Extract DPO preference pairs from logs."""
        ...


class AbstractSyntheticGenerator(ABC):
    """Abstract interface for generating grounded chosen responses."""

    @abstractmethod
    def generate_grounded_chosen(self, prompt: str, context: str | None) -> str:
        """Generate a grounded chosen completion."""
        ...


class AbstractDPOTrainerBridge(ABC):
    """Abstract interface for executing DPO training epochs."""

    @abstractmethod
    def train_epoch(self, dataset_path: Path, epoch_id: str) -> tuple[float, float]:
        """Execute a DPO training epoch, returning (initial_loss, final_loss)."""
        ...


class AbstractDeploymentGate(ABC):
    """Abstract interface for evaluating and deploying post-DPO models."""

    @abstractmethod
    def evaluate_and_deploy(self, epoch_id: str) -> bool:
        """Run evaluation gates and deploy if passed."""
        ...
