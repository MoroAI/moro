"""SDK evaluation uses the same inference, evidence, and persistence as the CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path

from moro.config.loader import load_config
from moro.eval.runner import run_suite
from moro.export.eligibility import resolve_export_run
from moro.storage import db


class EvalHarness:
    def __init__(self, project_root: Path, experiment_tracker=None):
        self.project_root = Path(project_root).resolve()
        self.experiment_tracker = experiment_tracker

    def run_evaluation(self, run_id, eval_suite_path):
        cfg = load_config(self.project_root / "moro.yaml")
        suite = Path(eval_suite_path)
        if not suite.is_absolute():
            suite = self.project_root / suite
        selected = resolve_export_run(self.project_root, cfg.project.name, run_id)
        result = run_suite(
            suite_path=suite,
            model_path=str(selected.adapter_path),
            run_id=selected.id,
            local_only=cfg.project.privacy_mode == "local_only",
        )
        conn = db.get_connection(self.project_root)
        try:
            db.add_eval_run(
                conn=conn,
                run_id=selected.id,
                suite_name=result.suite_name,
                model=result.model,
                total_cases=result.total_cases,
                pass_rate=result.pass_rate,
                avg_score=result.avg_score,
                result=result.model_dump(mode="json"),
            )
        finally:
            conn.close()
        passed = sum(case.passed for case in result.cases)
        return {
            **result.model_dump(mode="json"),
            "eval_id": result.id,
            "passed_cases": passed,
            "failed_cases": result.total_cases - passed,
            "delta": None,
            "status": "completed",
        }

    async def run_evaluation_async(self, experiment_id, eval_suite_path, progress_callback=None):
        if progress_callback:
            progress_callback("Running model evaluation", None)
        result = await asyncio.to_thread(self.run_evaluation, experiment_id, eval_suite_path)
        if progress_callback:
            progress_callback("Evaluation completed", 100.0)
        return result
