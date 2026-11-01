"""
MoroAI Dashboard Dataset Management API.

Provides endpoints for:
- Dataset upload (drag-and-drop)
- Dataset listing and preview
- Dataset quality analysis
- Dataset compilation
"""

from __future__ import annotations

import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from moro.dashboard.uploads import (
    EXTENSIONS,
    delete_upload_metadata,
    read_upload_metadata,
    store_upload,
)
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
    upload_sha256: str | None = None


class DatasetUploadResponse(BaseModel):
    """Response after dataset upload."""

    dataset_id: str
    name: str
    path: str
    size_bytes: int
    message: str
    sha256: str


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
    if data_dir.is_symlink() or data_dir.parent.is_symlink():
        raise HTTPException(400, "Dataset directories must not be symbolic links")
    clean_id = dataset_id.removeprefix("ds_")
    if data_dir.exists():
        for file_path in data_dir.iterdir():
            if (
                not file_path.is_symlink()
                and file_path.is_file()
                and file_path.suffix.lower() in EXTENSIONS
                and (
                    file_path.stem == clean_id
                    or file_path.name == dataset_id
                    or file_path.stem == dataset_id
                )
            ):
                return file_path
    # Also check compiled
    compiled_dir = data_dir.parent / "compiled"
    if compiled_dir.is_symlink():
        raise HTTPException(400, "Dataset directories must not be symbolic links")
    if compiled_dir.exists():
        for file_path in compiled_dir.iterdir():
            if (
                not file_path.is_symlink()
                and file_path.is_file()
                and file_path.suffix.lower() in EXTENSIONS
                and (
                    file_path.stem == clean_id
                    or file_path.name == dataset_id
                    or file_path.stem == dataset_id
                )
            ):
                return file_path
    return None


def _snapshot_file(project_root: Path, dataset_id: str) -> Path | None:
    """Resolve a recorded immutable version only after checking its inventory."""
    from moro.core.errors import DatasetError
    from moro.data.versions import verify_snapshot
    from moro.storage import db

    conn = db.get_connection(project_root)
    try:
        row = conn.execute(
            "SELECT * FROM dataset_snapshots WHERE version_id=?", (dataset_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        verify_snapshot(project_root, row)
    except DatasetError as exc:
        raise HTTPException(409, "Dataset snapshot failed integrity verification") from exc
    return (project_root / row["manifest_path"]).parent / "dataset.jsonl"


def compile_dataset_sync(file_path: Path) -> str:
    """Compile a dataset synchronously or via background task."""
    from moro.data.compiler import DataCompiler

    project_root = get_project_root()
    compiler = DataCompiler(project_root)
    return compiler.compile_dataset(source_path=file_path)


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

    if data_dir.is_symlink() or data_dir.parent.is_symlink():
        raise HTTPException(400, "Dataset directories must not be symbolic links")

    if data_dir.exists():
        candidates = [p for p in data_dir.iterdir() if not p.is_symlink() and p.is_file()]
        for file_path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
            if (
                not file_path.is_symlink()
                and file_path.is_file()
                and file_path.suffix.lower()
                in [
                    ".jsonl",
                    ".json",
                    ".csv",
                    ".txt",
                ]
            ):
                # Count rows if small
                row_count = None
                try:
                    if file_path.stat().st_size < 10_000_000:
                        with open(file_path, encoding="utf-8", errors="ignore") as f:
                            row_count = sum(1 for line in f if line.strip())
                except Exception:
                    pass

                metadata = read_upload_metadata(file_path)
                datasets.append(
                    DatasetInfo(
                        id=f"ds_{file_path.stem}",
                        name=metadata.get("display_name", file_path.name),
                        path=str(file_path),
                        size_bytes=file_path.stat().st_size,
                        format=file_path.suffix.lstrip(".").lower(),
                        row_count=metadata.get("row_count", row_count),
                        upload_sha256=metadata.get("sha256"),
                        created_at=datetime.fromtimestamp(
                            file_path.stat().st_mtime, timezone.utc
                        ).isoformat(),
                        status="uploaded",
                    )
                )

    if compiled_dir.is_symlink():
        raise HTTPException(400, "Dataset directories must not be symbolic links")
    if compiled_dir.exists():
        for file_path in compiled_dir.iterdir():
            if (
                not file_path.is_symlink()
                and file_path.is_file()
                and file_path.suffix.lower() == ".jsonl"
            ):
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

    from moro.data.versions import verify_snapshot
    from moro.storage import db

    conn = db.get_connection(project_root)
    try:
        snapshots = conn.execute(
            "SELECT s.*, v.created_at FROM dataset_snapshots s JOIN dataset_versions v ON v.id=s.version_id ORDER BY v.created_at DESC"
        ).fetchall()
        for row in snapshots:
            try:
                verify_snapshot(project_root, row)
                file = (project_root / row["manifest_path"]).parent / "dataset.jsonl"
                datasets.append(
                    DatasetInfo(
                        id=row["version_id"],
                        name=row["version_id"],
                        path=str(file),
                        size_bytes=file.stat().st_size,
                        format="jsonl",
                        created_at=row["created_at"],
                        status="compiled",
                    )
                )
            except Exception:
                # Damaged snapshots must not be presented as ready for training.
                continue
    finally:
        conn.close()

    return datasets


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str = Form(None),
    auto_compile: bool = Form(False),
    display_name: str | None = Form(None),
) -> DatasetUploadResponse:
    """Upload a dataset file (JSONL, JSON, CSV, TXT) to data/raw/."""
    project_root = get_project_root()
    file_path = await asyncio.to_thread(
        store_upload, project_root, file, name, display_name=display_name
    )
    metadata = read_upload_metadata(file_path)
    dataset_name = metadata["display_name"]
    dataset_id = f"ds_{file_path.stem}"
    file_size = file_path.stat().st_size

    if auto_compile:
        try:
            await asyncio.to_thread(compile_dataset_sync, file_path)
        except Exception as exc:
            raise HTTPException(
                422,
                {
                    "message": "Upload saved, compilation failed",
                    "dataset_id": dataset_id,
                    "error": str(exc),
                },
            ) from exc

    return DatasetUploadResponse(
        dataset_id=dataset_id,
        name=dataset_name,
        path=str(file_path),
        size_bytes=file_size,
        message=f"Dataset uploaded successfully. Size: {file_size / 1024:.1f} KB",
        sha256=metadata["sha256"],
    )


@router.post("/upload/multiple")
async def upload_multiple_datasets(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    auto_compile: bool = Form(False),
) -> dict:
    """Upload multiple dataset files simultaneously."""
    if not files or len(files) > 20:
        raise HTTPException(400, "Upload between 1 and 20 files")
    results = []
    for file in files:
        try:
            result = await upload_dataset(
                background_tasks,
                file=file,
                name=None,
                auto_compile=auto_compile,
                display_name=None,
            )
        except HTTPException as exc:
            saved = isinstance(exc.detail, dict) and "dataset_id" in exc.detail
            results.append(
                {
                    "filename": file.filename,
                    "status": "saved_compile_failed" if saved else "rejected",
                    "status_code": exc.status_code,
                    "detail": exc.detail,
                }
            )
        else:
            results.append({**result.model_dump(), "status": "uploaded"})
    return {"results": results, "total_uploaded": sum(r["status"] != "rejected" for r in results)}


@router.get("/{dataset_id}/preview", response_model=DatasetPreview)
async def preview_dataset(dataset_id: str, limit: int = Query(10, ge=1, le=100)) -> DatasetPreview:
    """Preview the sample rows and schema of a dataset."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"

    dataset_file = _snapshot_file(project_root, dataset_id) or _find_dataset_file(
        data_dir, dataset_id
    )
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    rows: list[dict] = []
    columns: set[str] = set()

    try:
        row_count = 0
        if dataset_file.suffix == ".jsonl":
            with open(dataset_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row_count += 1
                    if len(rows) >= limit:
                        continue
                    try:
                        row = json.loads(line)
                        if isinstance(row, dict):
                            rows.append(row)
                            columns.update(row.keys())
                    except json.JSONDecodeError:
                        continue

        elif dataset_file.suffix == ".json":
            with open(dataset_file, encoding="utf-8") as f:
                value = json.load(f)
            records = value if isinstance(value, list) else [value]
            if any(not isinstance(row, dict) for row in records):
                raise ValueError("JSON must contain records")
            row_count = len(records)
            rows = records[:limit]
            for row in rows:
                columns.update(row)
        elif dataset_file.suffix == ".csv":
            with open(dataset_file, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row_count += 1
                    if len(rows) < limit:
                        rows.append(dict(row))
                        columns.update(row.keys())
        else:
            with open(dataset_file, encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    if line.strip():
                        row_count += 1
                        if len(rows) < limit:
                            rows.append({"text": line.strip()})
                columns.add("text")

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

    if _snapshot_file(project_root, dataset_id) is not None:
        raise HTTPException(409, "Dataset version is already compiled; compile its source instead")

    dataset_file = _find_dataset_file(data_dir, dataset_id)
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    try:
        version = await asyncio.to_thread(compile_dataset_sync, dataset_file)
    except Exception as exc:
        raise HTTPException(422, f"Dataset compilation failed: {exc}") from exc
    return {"dataset_id": dataset_id, "version_id": version, "status": "compiled"}


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict:
    """Delete a raw or compiled dataset."""
    project_root = get_project_root()
    data_dir = project_root / "data" / "raw"

    if _snapshot_file(project_root, dataset_id) is not None:
        raise HTTPException(409, "Immutable dataset versions cannot be deleted through this API")

    dataset_file = _find_dataset_file(data_dir, dataset_id)
    if not dataset_file or not dataset_file.exists():
        raise HTTPException(status_code=404, detail=f"Dataset {dataset_id} not found")

    dataset_file.unlink()
    delete_upload_metadata(dataset_file)
    return {"dataset_id": dataset_id, "status": "deleted"}
