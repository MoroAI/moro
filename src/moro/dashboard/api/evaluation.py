"""
MoroAI Dashboard Evaluation API.

Provides endpoints for:
- Listing evaluation test suites
- Running evaluation suites against trained models
- Fetching and comparing evaluation test results
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from moro.dashboard.utils import get_project_root

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


class EvalRunRequest(BaseModel):
    """Request to run an evaluation suite."""

    run_id: str
    suite_path: str = "eval/sample_suite.yaml"


class EvalResultItem(BaseModel):
    """Evaluation result structure."""

    run_id: str
    suite_name: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate: float
    status: str = "completed"


@router.get("/suites")
async def list_evaluation_suites() -> dict:
    """List available evaluation test suites."""
    project_root = get_project_root()
    eval_dir = project_root / "eval"
    quickstart_eval = project_root / "examples" / "quickstart" / "eval"

    suites: list[dict] = []
    for d in [eval_dir, quickstart_eval]:
        if d.exists():
            for p in d.glob("*.yaml"):
                suites.append(
                    {
                        "name": p.stem,
                        "path": str(p),
                        "size_bytes": p.stat().st_size,
                    }
                )
    return {"suites": suites}


@router.post("/run", response_model=EvalResultItem)
async def run_evaluation(request: EvalRunRequest) -> EvalResultItem:
    """Run an evaluation suite against a training run."""
    project_root = get_project_root()
    suite_path = Path(request.suite_path)
    if not suite_path.is_absolute():
        suite_path = project_root / suite_path

    from moro.eval.harness import EvalHarness

    harness = EvalHarness(project_root)

    root = project_root.resolve()
    if not suite_path.resolve().is_relative_to(root) or suite_path.is_symlink():
        raise HTTPException(422, "Evaluation suite must be inside the project")
    if not suite_path.is_file():
        raise HTTPException(404, "Evaluation suite not found")
    from moro.core.errors import ConfigError, DependencyError, EvalError, ExportError

    try:
        res = await harness.run_evaluation_async(request.run_id, suite_path)
    except DependencyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ConfigError, EvalError, ExportError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return EvalResultItem(**res)


@router.get("/results/{run_id}")
async def get_eval_results(run_id: str) -> dict:
    """Get evaluation results for a training run."""
    from moro.storage import db

    conn = db.get_connection(get_project_root())
    try:
        row = conn.execute(
            "SELECT result_json FROM eval_runs WHERE run_id=? ORDER BY created_at DESC LIMIT 1",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(404, "No recorded evaluation for this run")
    return json.loads(row["result_json"])
