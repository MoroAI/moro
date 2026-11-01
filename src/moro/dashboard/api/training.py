"""Real training execution and recorded run inspection.

Execution is awaited; this API does not claim durable scheduling or cancellation.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from moro.dashboard.utils import get_project_root
from moro.storage import db

router = APIRouter(prefix="/api/training", tags=["training"])


class TrainingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_name: str | None = None
    dataset_id: str | None = None
    learning_rate: float | None = Field(None, gt=0)
    batch_size: int | None = Field(None, ge=1)
    epochs: float | None = Field(None, gt=0)
    lora_r: int | None = Field(None, ge=1, le=256)
    lora_alpha: int | None = Field(None, ge=1, le=512)
    max_seq_length: int | None = Field(None, ge=16, le=32768)
    gradient_checkpointing: bool | None = None


def recorded_runs():
    conn = db.get_connection(get_project_root())
    try:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        return [
            {
                **dict(row),
                "run_id": row["id"],
                "current_loss": row["train_loss"],
                "current_step": None,
                "total_steps": None,
            }
            for row in rows
        ]
    finally:
        conn.close()


@router.get("/runs")
async def list_training_runs(status: str | None = None, limit: int = Query(50, ge=1, le=500)):
    return [row for row in recorded_runs() if status is None or row["status"] == status][:limit]


@router.get("/runs/{run_id}")
async def get_training_run(run_id: str):
    for row in recorded_runs():
        if row["run_id"] == run_id:
            return row
    raise HTTPException(404, "Training run not found")


@router.post("/start")
async def start_training(config: TrainingConfig):
    from moro.core.errors import ConfigError, DatasetError, DependencyError, TrainingError
    from moro.training.runner import TrainingRunner

    runner = TrainingRunner(get_project_root())
    try:
        result = await asyncio.to_thread(runner.run_training, config.model_dump(exclude_none=True))
    except DependencyError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ConfigError, DatasetError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except TrainingError as exc:
        raise HTTPException(409, str(exc)) from exc
    return dict(result.items())


@router.post("/runs/{run_id}/stop")
@router.post("/runs/{run_id}/cancel")
async def stop_training(run_id: str):
    await get_training_run(run_id)
    raise HTTPException(
        409, "Process cancellation is not implemented; no cancellation was performed"
    )


@router.post("/runs/{run_id}/resume")
async def resume_training(run_id: str):
    await get_training_run(run_id)
    raise HTTPException(
        409, "Checkpoint resume is not implemented; no training was started"
    )


@router.get("/runs/{run_id}/metrics")
async def get_training_metrics(run_id: str):
    row = await get_training_run(run_id)
    return {
        "run_id": run_id,
        "status": row["status"],
        "current_loss": row["train_loss"],
        "peak_vram_gb": row["peak_vram_gb"],
        "current_step": None,
        "total_steps": None,
        "progress_percent": None,
    }


@router.get("/gpu/status")
async def get_gpu_status() -> dict:
    """Inspect system GPU status and VRAM allocations."""
    try:
        import torch

        if torch.cuda.is_available():
            device_count = torch.cuda.device_count()
            devices = [
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "memory_total_gb": round(
                        torch.cuda.get_device_properties(i).total_memory / (1024**3), 2
                    ),
                    "memory_allocated_gb": round(torch.cuda.memory_allocated(i) / (1024**3), 2),
                    "memory_reserved_gb": round(torch.cuda.memory_reserved(i) / (1024**3), 2),
                }
                for i in range(device_count)
            ]
            return {
                "available": True,
                "device_count": device_count,
                "devices": devices,
            }
        return {"available": False, "message": "No CUDA device detected (CPU mode)"}
    except ImportError:
        return {"available": False, "message": "PyTorch not installed"}
