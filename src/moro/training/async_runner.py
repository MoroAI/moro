"""Asynchronous adapter for real training; no generated metrics or pretend artifacts."""

from __future__ import annotations

import asyncio
from pathlib import Path


class AsyncTrainingRunner:
    def __init__(self, project_root: Path, experiment_tracker=None):
        self.project_root = Path(project_root)
        self.experiment_tracker = experiment_tracker

    async def run_training_async(self, experiment_id, dataset_id, recipe, progress_callback=None):
        from moro.training.runner import TrainingRunner

        runner = TrainingRunner(self.project_root, self.experiment_tracker)
        # Cancelling this await does not stop an already running backend thread.
        # The caller must not interpret cancellation as confirmed training termination.
        result = await asyncio.to_thread(
            runner.run_training,
            recipe=recipe,
            dataset_id=dataset_id,
            progress_callback=progress_callback,
        )
        return dict(result.items())
