"""
MoroAI Dashboard Model Management API.

Provides endpoints for:
- Listing registered and released models
- Comparing models side-by-side
- Promoting models to production
- Archiving and deleting models
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from moro.dashboard.utils import get_project_root, get_state_db_path

router = APIRouter(prefix="/api/models", tags=["models"])


# ===================================================================
# MODELS
# ===================================================================


class ModelInfo(BaseModel):
    """Information about a model in the registry."""

    model_id: str
    model_name: str
    version: str
    base_model: str | None = None
    quantization: str | None = None
    adapter_type: str | None = None
    lora_rank: int | None = None
    eval_pass_rate: float | None = None
    eval_delta: float | None = None
    status: str = "released"  # trained, released, deployed, archived
    is_production: bool = False
    trained_at: str | None = None
    deployed_at: str | None = None


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================


def _measured_float(value: object) -> float | None:
    """Return a measured metric, preserving the None-vs-0.0 distinction.

    Unmeasured (missing/None) stays None; a measured 0.0 stays 0.0.
    Bools and non-numeric payloads are treated as unmeasured rather
    than coerced into a fabricated score.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _get_models_from_releases(project_root: Path) -> list[dict]:
    """Scan releases/ directory on filesystem."""
    releases_dir = project_root / "releases"
    models: list[dict] = []
    if not releases_dir.exists():
        return models

    for rel_dir in releases_dir.iterdir():
        if rel_dir.is_dir():
            meta_path = rel_dir / "metadata.json"
            eval_results: object = {}
            created_at = datetime.fromtimestamp(rel_dir.stat().st_mtime, timezone.utc).isoformat()

            if meta_path.exists():
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        meta = json.load(f)
                        eval_results = meta.get("eval_results") or {}
                        created_at = meta.get("created_at", created_at)
                except Exception:
                    pass

            results = eval_results if isinstance(eval_results, dict) else {}
            pass_rate = _measured_float(results.get("pass_rate"))
            eval_delta: float | None = None
            for key in ("eval_delta", "pass_rate_delta", "delta"):
                eval_delta = _measured_float(results.get(key))
                if eval_delta is not None:
                    break

            models.append(
                {
                    "model_id": f"mod_{rel_dir.name}",
                    "model_name": f"moro-{rel_dir.name}",
                    "version": rel_dir.name,
                    "base_model": None,
                    "quantization": None,
                    "adapter_type": None,
                    "lora_rank": None,
                    "eval_pass_rate": pass_rate,
                    "eval_delta": eval_delta,
                    "status": "released",
                    "is_production": False,
                    "trained_at": created_at,
                    "deployed_at": None,
                }
            )

    return models


# ===================================================================
# ENDPOINTS
# ===================================================================


@router.get("/", response_model=list[ModelInfo])
async def list_models(status: str | None = None, production_only: bool = False) -> list[ModelInfo]:
    """List all registered and released models."""
    project_root = get_project_root()
    db_path = get_state_db_path()

    registered_models: list[dict] = []
    if db_path.exists():
        try:
            from moro.state.manager import StateManager

            state_manager = StateManager(db_path)
            registered_models = state_manager.list_models(
                status=status, production_only=production_only
            )
        except Exception:
            pass

    # Merge filesystem releases if not in DB
    fs_models = _get_models_from_releases(project_root)
    existing_ids = {m.get("model_id") for m in registered_models}

    for fm in fs_models:
        if fm["model_id"] not in existing_ids:
            if not production_only or fm["is_production"]:
                if status is None or fm["status"] == status:
                    registered_models.append(fm)

    return [ModelInfo(**m) for m in registered_models]


@router.get("/{model_id}", response_model=ModelInfo)
async def get_model(model_id: str) -> ModelInfo:
    """Get details for a specific model."""
    all_models = await list_models()
    for m in all_models:
        if m.model_id == model_id or m.version == model_id:
            return m
    raise HTTPException(status_code=404, detail=f"Model {model_id} not found")


@router.post("/{model_id}/promote")
async def promote_model(model_id: str) -> dict:
    """Select only a recorded model whose real release policy passes."""
    db_path = get_state_db_path()
    if not db_path.exists():
        raise HTTPException(404, "Model not found")
    from moro.state.manager import StateManager

    try:
        promoted = StateManager(db_path).promote_model_to_production(model_id)
    except Exception as exc:
        raise HTTPException(
            409, "Model is not eligible for promotion; verify its training and evaluation evidence"
        ) from exc
    if not promoted:
        raise HTTPException(404, "Model not found")
    return {
        "model_id": model_id,
        "is_production": True,
        "status": "selected",
        "message": "Evaluated model selected; runtime deployment is a separate operation.",
    }


@router.post("/{model_id}/archive")
async def archive_model(model_id: str) -> dict:
    """Archive a model."""
    return _mutate_registry(model_id, "archive")


@router.delete("/{model_id}")
async def delete_model(model_id: str) -> dict:
    return _mutate_registry(model_id, "delete")


def _mutate_registry(model_id, action):
    path = get_state_db_path()
    if not path.exists():
        raise HTTPException(404, "Model not found")
    from moro.state.manager import StateManager

    conn = StateManager(path)._get_conn()
    try:
        with conn:
            if action == "archive":
                cursor = conn.execute(
                    "UPDATE model_registry SET status='archived', is_production=0 WHERE model_id=?",
                    (model_id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM model_registry WHERE model_id=? AND is_production=0", (model_id,)
                )
            if cursor.rowcount == 0:
                if conn.execute(
                    "SELECT 1 FROM model_registry WHERE model_id=?", (model_id,)
                ).fetchone():
                    raise HTTPException(
                        409, "Archive the selected model before deleting its registry entry"
                    )
                raise HTTPException(404, "Model not found")
    finally:
        conn.close()
    return {"model_id": model_id, "status": "archived" if action == "archive" else "deleted"}


@router.get("/compare/{model_a_id}/{model_b_id}")
async def compare_models(model_a_id: str, model_b_id: str) -> dict:
    """Compare two models side-by-side with automatic winner evaluation."""
    all_models = await list_models()
    model_a = next(
        (m for m in all_models if m.model_id == model_a_id or m.version == model_a_id), None
    )
    model_b = next(
        (m for m in all_models if m.model_id == model_b_id or m.version == model_b_id), None
    )

    if not model_a or not model_b:
        raise HTTPException(status_code=404, detail="One or both models not found for comparison")

    if model_a.eval_pass_rate is None or model_b.eval_pass_rate is None:
        raise HTTPException(409, "Comparison requires measured evaluation results for both models")
    # A measured 0.0 is a real score; only unmeasured (None) delta is
    # omitted from the ranking, and the basis is disclosed.
    assert model_a.eval_pass_rate is not None and model_b.eval_pass_rate is not None
    if model_a.eval_delta is None or model_b.eval_delta is None:
        score_a = model_a.eval_pass_rate
        score_b = model_b.eval_pass_rate
        winner_basis = "eval_pass_rate"
    else:
        score_a = model_a.eval_pass_rate + model_a.eval_delta
        score_b = model_b.eval_pass_rate + model_b.eval_delta
        winner_basis = "eval_pass_rate+eval_delta"
    winner = model_a.model_id if score_a >= score_b else model_b.model_id

    return {
        "comparison": {
            "model_a": model_a.model_dump(),
            "model_b": model_b.model_dump(),
            "metrics": {
                "eval_pass_rate": {
                    "model_a": model_a.eval_pass_rate,
                    "model_b": model_b.eval_pass_rate,
                },
                "eval_delta": {
                    "model_a": model_a.eval_delta,
                    "model_b": model_b.eval_delta,
                },
            },
        },
        "winner": winner,
        "winner_basis": winner_basis,
    }
