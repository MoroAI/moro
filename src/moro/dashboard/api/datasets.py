"""
MoroAI Dashboard Dataset Management API.

Provides endpoints for:
- Dataset upload (drag-and-drop)
- Dataset listing and preview
- Dataset quality analysis
- Dataset compilation
"""

from __future__ import annotations

import csv
import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from moro.dashboard.utils import get_project_root

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


# ===================================================================
# MODELS
# ===================================================================


class DatasetInfo(BaseModel):
    """Information about a dataset."""

    id: str
    name: str
    path: str
    size_bytes: int
    format: str
    row_count: int | None = None
    created_at: str
    status: str = "uploaded"  # uploaded, compiling, compiled, failed


class DatasetUploadResponse(BaseModel):
    """Response after dataset upload."""

    dataset_id: str
    name: str
    path: str
    size_bytes: int
    message: str


class DatasetPreview(BaseModel):
    """Preview of dataset contents."""

    dataset_id: str
    row_count: int
    columns: list[str]
    sample_rows: list[dict]
    quality_metrics: dict


# ===================================================================
# HELPER FUNCTIONS
# ===================================================================


def _find_dataset_file(data_dir: Path, dataset_id: str) -> Path | None:
    """Find a dataset file by id or name."""
    clean_id = dataset_id.removeprefix("ds_")
    if data_dir.exists():
        for file_path in data_dir.iterdir():
            if file_path.is_file() and (
                file_path.stem == clean_id
                or file_path.name == dataset_id
                or file_path.stem == dataset_id
            ):
                return file_path
    # Also check compiled
    compiled_dir = data_dir.parent / "compiled"
    if compiled_dir.exists():
        for file_path in compiled_dir.iterdir():
            if file_path.is_file() and (
                file_path.stem == clean_id
                or file_path.name == dataset_id
                or file_path.stem == dataset_id
            ):
                return file_path
    return None


def compile_dataset_sync(file_path: Path) -> None:
    """Compile a dataset synchronously or via background task."""
    from moro.data.compiler import DataCompiler

    project_root = get_project_root()
    try:
        compiler = DataCompiler(project_root)
        compiler.compile_dataset(
            source_path=file_path,
            config={"format": "auto", "deduplicate": True},
        )
    except Exception as exc:
        print(f"Dataset compilation failed for {file_path}: {exc}")


# ===================================================================
# ENDPOINTS
# ===================================================================


@router.get("/", response_model=list[DatasetInfo])
async def list_datasets() -> list[DatasetInfo]:
    """List all raw and compiled datasets in the project."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"
    compiled_dir = project_root / "data" / "compiled"

    datasets: list[DatasetInfo] = []

    if data_dir.exists():
        for file_path in sorted(data_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if file_path.is_file() and file_path.suffix.lower() in [
                ".jsonl",
                ".json",
                ".csv",
                ".txt",
            ]:
                # Count rows if small
                row_count = None
                try:
                    if file_path.stat().st_size < 10_000_000:
                        with open(file_path, encoding="utf-8", errors="ignore") as f:
                            row_count = sum(1 for line in f if line.strip())
                except Exception:
                    pass

                datasets.append(
                    DatasetInfo(
                        id=f"ds_{file_path.stem}",
                        name=file_path.name,
                        path=str(file_path),
                        size_bytes=file_path.stat().st_size,
                        format=file_path.suffix.lstrip(".").lower(),
                        row_count=row_count,
                        created_at=datetime.fromtimestamp(
                            file_path.stat().st_mtime, timezone.utc
                        ).isoformat(),
                        status="uploaded",
                    )
                )

    if compiled_dir.exists():
        for file_path in compiled_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() == ".jsonl":
                row_count = None
                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        row_count = sum(1 for line in f if line.strip())
                except Exception:
                    pass

                datasets.append(
                    DatasetInfo(
                        id=f"compiled_{file_path.stem}",
                        name=f"compiled/{file_path.name}",
                        path=str(file_path),
                        size_bytes=file_path.stat().st_size,
                        format="jsonl",
                        row_count=row_count,
                        created_at=datetime.fromtimestamp(
                            file_path.stat().st_mtime, timezone.utc
                        ).isoformat(),
                        status="compiled",
                    )
                )

    return datasets


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(None),
    auto_compile: bool = Form(False),
) -> DatasetUploadResponse:
    """Upload a dataset file (JSONL, JSON, CSV, TXT) to data/raw/."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or f"upload_{uuid.uuid4().hex[:6]}.jsonl"
    file_ext = Path(filename).suffix.lower()
    allowed_extensions = {".jsonl", ".json", ".csv", ".txt"}

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file_ext}. Allowed: {sorted(allowed_extensions)}",
        )

    dataset_name = name if name else filename
    dataset_id = f"ds_{Path(dataset_name).stem}"
    file_path = data_dir / dataset_name

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = file_path.stat().st_size

    if auto_compile:
        background_tasks.add_task(compile_dataset_sync, file_path)

    return DatasetUploadResponse(
        dataset_id=dataset_id,
        name=dataset_name,
        path=str(file_path),
        size_bytes=file_size,
        message=f"Dataset uploaded successfully. Size: {file_size / 1024:.1f} KB",
    )


@router.post("/upload/multiple")
async def upload_multiple_datasets(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    auto_compile: bool = Form(False),
) -> dict:
    """Upload multiple dataset files simultaneously."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)

    results = []
    allowed_extensions = {".jsonl", ".json", ".csv", ".txt"}

    for file in files:
        filename = file.filename or f"upload_{uuid.uuid4().hex[:6]}.jsonl"
        file_ext = Path(filename).suffix.lower()

        if file_ext not in allowed_extensions:
            results.append(
                {
                    "filename": filename,
                    "status": "skipped",
                    "reason": f"Invalid file type: {file_ext}",
                }
            )
            continue

        file_path = data_dir / filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        if auto_compile:
            background_tasks.add_task(compile_dataset_sync, file_path)

        results.append(
            {
                "filename": filename,
                "status": "uploaded",
                "size_bytes": file_path.stat().st_size,
            }
        )

    return {
        "results": results,
        "total_uploaded": sum(1 for r in results if r["status"] == "uploaded"),
    }


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
async def preview_dataset(dataset_id: str, limit: int = 10) -> DatasetPreview:
    """Preview the sample rows and schema of a dataset."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"

    dataset_file = _find_dataset_file(data_dir, dataset_id)
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    rows: list[dict] = []
    columns: set[str] = set()

    try:
        if dataset_file.suffix == ".jsonl":
            with open(dataset_file, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    if i >= limit:
                        break
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            rows.append(row)
                            columns.update(row.keys())
                    except json.JSONDecodeError:
                        continue

        elif dataset_file.suffix == ".csv":
            with open(dataset_file, encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= limit:
                        break
                    rows.append(dict(row))
                    columns.update(row.keys())
        else:
            with open(dataset_file, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if i >= limit:
                        break
                    rows.append({"text": line.strip()})
                columns.add("text")

        # Total rows count
        row_count = 0
        with open(dataset_file, encoding="utf-8", errors="ignore") as f:
            row_count = sum(1 for line in f if line.strip())

        quality_metrics = {
            "total_rows": row_count,
            "sample_size": len(rows),
            "columns": len(columns),
            "avg_row_size": sum(len(json.dumps(r)) for r in rows) / len(rows) if rows else 0,
        }

        return DatasetPreview(
            dataset_id=dataset_id,
            row_count=row_count,
            columns=sorted(columns),
            sample_rows=rows,
            quality_metrics=quality_metrics,
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to preview dataset: {exc}")


@router.post("/{dataset_id}/compile")
async def compile_dataset(dataset_id: str, background_tasks: BackgroundTasks) -> dict:
    """Compile a dataset into training-ready format."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"

    dataset_file = _find_dataset_file(data_dir, dataset_id)
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    background_tasks.add_task(compile_dataset_sync, dataset_file)

    return {
        "dataset_id": dataset_id,
        "status": "compiling",
        "message": f"Compilation started for {dataset_file.name}",
    }


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict:
    """Delete a raw or compiled dataset."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"

    dataset_file = _find_dataset_file(data_dir, dataset_id)
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    dataset_file.unlink()
    return {"dataset_id": dataset_id, "status": "deleted"}
