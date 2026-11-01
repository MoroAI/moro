"""Strict administrative operations backed by the real application services.

The application-wide security middleware protects this router. Operations are
awaited: run identifiers refer to recorded training runs, not queued jobs.
"""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from moro.dashboard.api import datasets, training

router = APIRouter(prefix="/api/operations", tags=["operations"])
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")]


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ListDatasetsRequest(StrictRequest):
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0, le=1_000_000)


class PreviewDatasetRequest(StrictRequest):
    dataset_id: Identifier
    row_limit: int = Field(10, ge=1, le=100)


class CompileDatasetRequest(StrictRequest):
    dataset_id: Identifier


class StartTrainingRequest(training.TrainingConfig):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    dataset_id: Identifier


class JobRequest(StrictRequest):
    job_id: Identifier


class OperationResponse(BaseModel):
    operation: str
    ok: bool
    payload: dict[str, Any]


async def _list_datasets(request):
    rows = await datasets.list_datasets()
    return {
        "datasets": [r.model_dump() for r in rows[request.offset : request.offset + request.limit]],
        "total": len(rows),
    }


async def _preview_dataset(request):
    return (await datasets.preview_dataset(request.dataset_id, request.row_limit)).model_dump()


async def _compile_dataset(request):
    return await datasets.compile_dataset(request.dataset_id, BackgroundTasks())


async def _start_training(request):
    return await training.start_training(request)


async def _get_job_status(request):
    return await training.get_training_run(request.job_id)


async def _stop_job(request):
    # Until a process-owning worker exists, this raises 409 for a recorded run.
    # A cancellation request must never be reported as confirmed termination.
    return await training.stop_training(request.job_id)


async def _resume_job(request):
    # No resume path validates checkpoints, so this raises 409 for a recorded
    # run instead of starting unvalidated training.
    return await training.resume_training(request.job_id)


HANDLERS = {
    "list_datasets": (ListDatasetsRequest, _list_datasets),
    "preview_dataset": (PreviewDatasetRequest, _preview_dataset),
    "compile_dataset": (CompileDatasetRequest, _compile_dataset),
    "start_training": (StartTrainingRequest, _start_training),
    "get_job_status": (JobRequest, _get_job_status),
    "stop_job": (JobRequest, _stop_job),
    "resume_job": (JobRequest, _resume_job),
}


@router.post("/{operation}", response_model=OperationResponse)
async def dispatch(operation: str, body: dict[str, Any]):
    registered = HANDLERS.get(operation)
    if registered is None:
        raise HTTPException(404, "Unknown operation")
    schema, handler = registered
    try:
        request = schema.model_validate(body)
    except ValidationError as exc:
        # Do not echo submitted values (potential secrets) in validation errors.
        raise HTTPException(
            422, exc.errors(include_url=False, include_context=False, include_input=False)
        ) from exc
    return OperationResponse(operation=operation, ok=True, payload=await handler(request))
