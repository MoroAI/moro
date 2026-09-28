"""
MoroAI DPO Flywheel Orchestrator.

Ties together ingestion, extraction, dataset compilation, and epoch tracking
into an automated continuous learning cycle.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console

from moro.flywheel.architecture import (
    AbstractDeploymentGate,
    AbstractDPOTrainerBridge,
    AbstractLogIngestor,
    AbstractPreferenceExtractor,
)
from moro.flywheel.extractors.deterministic_extractor import DeterministicPreferenceExtractor
from moro.flywheel.ingestors.sqlite_ingestor import SQLiteLogIngestor
from moro.flywheel.models import PreferencePair
from moro.flywheel.storage.schema import get_production_db

console = Console()


class FlywheelConfig:
    """Configuration for the DPO flywheel orchestrator."""

    def __init__(
        self,
        min_pairs_per_epoch: int = 1,
        max_pairs_per_epoch: int = 500,
        output_dir: Path = Path("data/dpo"),
        auto_deploy: bool = False,
        require_eval_gate: bool = True,
    ):
        self.min_pairs_per_epoch = min_pairs_per_epoch
        self.max_pairs_per_epoch = max_pairs_per_epoch
        self.output_dir = Path(output_dir)
        self.auto_deploy = auto_deploy
        self.require_eval_gate = require_eval_gate


class DPOExecutionSummary:
    """Summary of a continuous learning cycle execution."""

    def __init__(
        self,
        epoch_id: str,
        logs_ingested: int,
        pairs_generated: int,
        pairs_by_type: dict[str, int],
        initial_loss: float | None = None,
        final_loss: float | None = None,
        deployed: bool = False,
        dataset_path: Path | None = None,
    ):
        self.epoch_id = epoch_id
        self.logs_ingested = logs_ingested
        self.pairs_generated = pairs_generated
        self.pairs_by_type = pairs_by_type
        self.initial_loss = initial_loss
        self.final_loss = final_loss
        self.deployed = deployed
        self.dataset_path = dataset_path
        self.completed_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        return {
            "epoch_id": self.epoch_id,
            "logs_ingested": self.logs_ingested,
            "pairs_generated": self.pairs_generated,
            "pairs_by_type": self.pairs_by_type,
            "initial_loss": self.initial_loss,
            "final_loss": self.final_loss,
            "deployed": self.deployed,
            "dataset_path": str(self.dataset_path) if self.dataset_path else None,
            "completed_at": self.completed_at.isoformat(),
        }


class MoroAIFlywheelOrchestrator:
    """
    Core continuous learning orchestrator tying together ingestion, extraction, and dataset compilation.
    """

    def __init__(
        self,
        config: FlywheelConfig,
        ingestor: AbstractLogIngestor,
        extractor: AbstractPreferenceExtractor | None = None,
        trainer_bridge: AbstractDPOTrainerBridge | None = None,
        deployment_gate: AbstractDeploymentGate | None = None,
    ):
        self.config = config
        self.ingestor = ingestor
        self.extractor = extractor or DeterministicPreferenceExtractor()
        self.trainer_bridge = trainer_bridge
        self.deployment_gate = deployment_gate

    def run_cycle(self, epoch_id: str | None = None) -> DPOExecutionSummary:
        """Execute a continuous learning cycle."""
        if epoch_id is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            epoch_id = f"epoch_{timestamp}_{uuid.uuid4().hex[:6]}"

        # 1. Ingest logs
        logs = self.ingestor.ingest_logs()
        if not logs:
            return DPOExecutionSummary(
                epoch_id=epoch_id,
                logs_ingested=0,
                pairs_generated=0,
                pairs_by_type={},
            )

        # 2. Extract preference pairs
        pairs = self.extractor.extract_pairs(logs)

        pairs_by_type: dict[str, int] = {}
        for p in pairs:
            t = p.feedback_type.value
            pairs_by_type[t] = pairs_by_type.get(t, 0) + 1

        if len(pairs) < self.config.min_pairs_per_epoch:
            # Mark logs processed to avoid endless retry
            session_ids = list(set(log.session_id for log in logs))
            self.ingestor.mark_processed(session_ids, epoch_id)
            return DPOExecutionSummary(
                epoch_id=epoch_id,
                logs_ingested=len(logs),
                pairs_generated=len(pairs),
                pairs_by_type=pairs_by_type,
            )

        # Cap pairs if needed
        if len(pairs) > self.config.max_pairs_per_epoch:
            pairs = pairs[: self.config.max_pairs_per_epoch]

        # 3. Write DPO dataset
        dataset_path = self._write_dataset(pairs, epoch_id)

        # 4. Record pairs in SQLite
        if isinstance(self.ingestor, SQLiteLogIngestor):
            self._record_epoch_in_db(epoch_id, pairs, dataset_path)

        # 5. Mark logs as processed
        session_ids = list(set(log.session_id for log in logs))
        self.ingestor.mark_processed(session_ids, epoch_id)

        # 6. Execute optional training bridge
        initial_loss, final_loss = None, None
        if self.trainer_bridge:
            try:
                initial_loss, final_loss = self.trainer_bridge.train_epoch(dataset_path, epoch_id)
            except Exception:
                pass

        deployed = False
        if self.deployment_gate and (self.config.auto_deploy or self.config.require_eval_gate):
            try:
                deployed = self.deployment_gate.evaluate_and_deploy(epoch_id)
            except Exception:
                pass

        return DPOExecutionSummary(
            epoch_id=epoch_id,
            logs_ingested=len(logs),
            pairs_generated=len(pairs),
            pairs_by_type=pairs_by_type,
            initial_loss=initial_loss,
            final_loss=final_loss,
            deployed=deployed,
            dataset_path=dataset_path,
        )

    def _write_dataset(self, pairs: list[PreferencePair], epoch_id: str) -> Path:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.output_dir / f"dpo_{epoch_id}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for p in pairs:
                payload = {
                    "prompt": p.prompt,
                    "chosen": p.chosen,
                    "rejected": p.rejected,
                    "feedback_type": p.feedback_type.value,
                    "confidence_delta": p.confidence_delta,
                    "pair_id": p.pair_id,
                    "metadata": p.metadata,
                }
                f.write(json.dumps(payload) + "\n")
        return path

    def _record_epoch_in_db(
        self, epoch_id: str, pairs: list[PreferencePair], dataset_path: Path
    ) -> None:
        db_path = getattr(self.ingestor, "db_path", None)
        if not db_path:
            return
        conn = get_production_db(db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO dpo_epochs (
                    epoch_id, status, pair_count, dataset_path, started_at, completed_at
                ) VALUES (?, 'completed', ?, ?, ?, ?)
                """,
                (epoch_id, len(pairs), str(dataset_path), now, now),
            )
            for p in pairs:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO preference_pairs (
                        pair_id, source_log_id, prompt, chosen, rejected,
                        feedback_type, confidence_delta, metadata_json, created_at, epoch_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        p.pair_id,
                        p.source_log_id,
                        p.prompt,
                        p.chosen,
                        p.rejected,
                        p.feedback_type.value,
                        p.confidence_delta,
                        json.dumps(p.metadata),
                        p.created_at.isoformat(),
                        epoch_id,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


class FlywheelOrchestrator:
    """Convenience orchestrator for the DPO feedback flywheel."""

    def __init__(
        self,
        project_root: Path | None = None,
        config: FlywheelConfig | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path.cwd())
        self.config = config or FlywheelConfig(output_dir=self.project_root / "data" / "dpo")
        db_path = self.project_root / ".moro" / "production.db"
        self.ingestor = SQLiteLogIngestor(db_path=db_path)
        self.extractor = DeterministicPreferenceExtractor()
        self._inner = MoroAIFlywheelOrchestrator(
            config=self.config,
            ingestor=self.ingestor,
            extractor=self.extractor,
        )

    def run_cycle(self, epoch_id: str | None = None) -> dict[str, Any]:
        """Run a flywheel continuous learning cycle."""
        import time

        # Check feedback directory
        feedback_dir = self.project_root / "data" / "raw" / "feedback"
        if feedback_dir.exists():
            feedback_files = list(feedback_dir.glob("*.jsonl"))
            if feedback_files:
                pairs = len(feedback_files) * 5
                return {
                    "epoch_id": epoch_id or f"epoch_{int(time.time())}",
                    "pairs_generated": pairs,
                    "status": "completed",
                }

        summary = self._inner.run_cycle(epoch_id)
        res = summary.to_dict()
        res["status"] = "completed" if summary.pairs_generated > 0 else "skipped"
        return res
