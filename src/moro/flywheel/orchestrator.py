"""
MoroAI DPO Flywheel Orchestrator.

Ties together ingestion, extraction, dataset compilation, and epoch tracking
into an automated continuous learning cycle.
"""

from __future__ import annotations

import json
import math
import os
import re
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
        if not 1 <= min_pairs_per_epoch <= max_pairs_per_epoch:
            raise ValueError("Pair limits must satisfy 1 <= minimum <= maximum")
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

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", epoch_id):
            raise ValueError("Invalid epoch ID")

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
            return DPOExecutionSummary(
                epoch_id=epoch_id,
                logs_ingested=len(logs),
                pairs_generated=0,
                pairs_by_type={},
            )

        # Cap pairs if needed
        if len(pairs) > self.config.max_pairs_per_epoch:
            pairs = pairs[: self.config.max_pairs_per_epoch]

        pairs_by_type = {}
        for pair in pairs:
            kind = pair.feedback_type.value
            pairs_by_type[kind] = pairs_by_type.get(kind, 0) + 1
            if not pair.source_log_id:
                raise ValueError("Preference pair must identify its source log")
            # Stable content identity prevents retry-dependent UUIDs.
            pair.pair_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    json.dumps([pair.source_log_id, pair.prompt, pair.chosen, pair.rejected, kind]),
                )
            )

        if isinstance(self.ingestor, SQLiteLogIngestor):
            dataset_path = self._record_epoch_in_db(epoch_id, pairs)
        else:
            dataset_path = self._write_dataset(pairs, epoch_id)
            self.ingestor.mark_processed(
                [], epoch_id, log_ids=sorted({p.source_log_id for p in pairs})
            )

        initial_loss, final_loss = None, None
        deployed = False
        try:
            if self.trainer_bridge:
                initial_loss, final_loss = self.trainer_bridge.train_epoch(dataset_path, epoch_id)
                if not all(
                    isinstance(v, (int, float)) and math.isfinite(v)
                    for v in (initial_loss, final_loss)
                ):
                    raise ValueError("Trainer returned invalid loss metrics")
                if self.config.auto_deploy:
                    if self.deployment_gate is None:
                        raise ValueError("Automatic deployment requires an evaluation gate")
                    deployed = self.deployment_gate.evaluate_and_deploy(epoch_id)
                self._update_epoch(epoch_id, "trained", initial_loss, final_loss, deployed)
            elif self.config.auto_deploy:
                raise ValueError("Cannot deploy an epoch without a successful trainer")
        except Exception:
            self._update_epoch(epoch_id, "failed", initial_loss, final_loss, False)
            raise

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
        with path.open("x", encoding="utf-8") as f:
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
            f.flush()
            os.fsync(f.fileno())
        return path

    def _record_epoch_in_db(self, epoch_id, pairs) -> Path:
        """Serialize publication and acknowledge only persisted source rows.

        An interrupted file write may leave an orphan requiring inspection, but
        cannot acknowledge pending logs or replace an existing epoch's dataset.
        """
        conn = get_production_db(self.ingestor.db_path)
        dataset_path = None
        try:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM dpo_epochs WHERE epoch_id=?", (epoch_id,)).fetchone():
                raise ValueError("Epoch ID already exists; use a new ID")
            ids = sorted({p.source_log_id for p in pairs})
            for source_id in ids:
                row = conn.execute(
                    "SELECT is_processed FROM inference_logs WHERE log_id=?", (source_id,)
                ).fetchone()
                if row is None or row["is_processed"]:
                    raise ValueError(
                        "Source log unavailable or already processed; retry extraction"
                    )
            now = datetime.now(timezone.utc).isoformat()
            dataset_path = self._write_dataset(pairs, epoch_id)
            conn.execute(
                "INSERT INTO dpo_epochs (epoch_id, status, pair_count, dataset_path, started_at, completed_at) VALUES (?, 'extracted', ?, ?, ?, ?)",
                (epoch_id, len(pairs), str(dataset_path), now, now),
            )
            for pair in pairs:
                conn.execute(
                    "INSERT INTO preference_pairs (pair_id, source_log_id, prompt, chosen, rejected, feedback_type, confidence_delta, metadata_json, created_at, epoch_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        pair.pair_id,
                        pair.source_log_id,
                        pair.prompt,
                        pair.chosen,
                        pair.rejected,
                        pair.feedback_type.value,
                        pair.confidence_delta,
                        json.dumps(pair.metadata),
                        pair.created_at.isoformat(),
                        epoch_id,
                    ),
                )
            conn.executemany(
                "UPDATE inference_logs SET is_processed=1, processed_at=?, epoch_id=? WHERE log_id=?",
                [(now, epoch_id, item) for item in ids],
            )
            conn.commit()
            return dataset_path
        except Exception:
            conn.rollback()
            # Only remove a file this transaction successfully created itself.
            if dataset_path is not None:
                dataset_path.unlink(missing_ok=True)
            raise
        finally:
            conn.close()

    def _update_epoch(self, epoch_id, status, initial_loss, final_loss, deployed):
        if not isinstance(self.ingestor, SQLiteLogIngestor):
            return
        conn = get_production_db(self.ingestor.db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE dpo_epochs SET status=?, initial_loss=?, final_loss=?, deployed=? WHERE epoch_id=?",
                    (status, initial_loss, final_loss, int(deployed), epoch_id),
                )
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
        db_path = self.project_root / "data" / "production_logs.db"
        self.ingestor = SQLiteLogIngestor(db_path=db_path)
        self.extractor = DeterministicPreferenceExtractor()
        self._inner = MoroAIFlywheelOrchestrator(
            config=self.config,
            ingestor=self.ingestor,
            extractor=self.extractor,
        )

    def run_cycle(self, epoch_id: str | None = None) -> dict[str, Any]:
        """Run a flywheel continuous learning cycle."""
        summary = self._inner.run_cycle(epoch_id)
        res = summary.to_dict()
        res["status"] = "extracted" if summary.dataset_path else "skipped"
        return res
