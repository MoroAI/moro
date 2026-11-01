"""Recorded feedback status and real preference extraction; no sample results."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Query
from pydantic import BaseModel

from moro.dashboard.utils import get_project_root
from moro.flywheel.storage.schema import get_db_stats, get_production_db

router = APIRouter(prefix="/api/flywheel", tags=["flywheel"])


class FlywheelCycleResponse(BaseModel):
    epoch_id: str
    pairs_generated: int
    status: str


@router.get("/status")
async def get_flywheel_status() -> dict:
    project_root = get_project_root()
    stats = get_db_stats(project_root / "data" / "production_logs.db")
    return {
        **stats,
        "status": "ready" if stats["pending_logs"] else "idle",
        "total_pairs_generated": stats["total_pairs"],
        "auto_deploy": False,
        "training_implemented": False,
    }


@router.post("/cycle", response_model=FlywheelCycleResponse)
async def trigger_flywheel_cycle() -> FlywheelCycleResponse:
    from moro.flywheel.orchestrator import FlywheelOrchestrator

    orchestrator = FlywheelOrchestrator(get_project_root())
    result = await asyncio.to_thread(orchestrator.run_cycle)
    return FlywheelCycleResponse(
        epoch_id=result["epoch_id"],
        pairs_generated=result["pairs_generated"],
        status=result["status"],
    )


@router.get("/pairs")
async def list_preference_pairs(limit: int = Query(20, ge=1, le=100)) -> dict:
    conn = get_production_db(get_project_root() / "data" / "production_logs.db")
    try:
        pairs = conn.execute(
            "SELECT pair_id, source_log_id, prompt, chosen, rejected, feedback_type, "
            "confidence_delta, created_at, epoch_id FROM preference_pairs "
            "ORDER BY created_at DESC, pair_id LIMIT ?",
            (limit,),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM preference_pairs").fetchone()[0]
        return {"pairs": [dict(row) for row in pairs], "total": total}
    finally:
        conn.close()
