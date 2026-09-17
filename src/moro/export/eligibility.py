"""Shared structural checks for export and deployment preparation.

These checks do not establish evaluation quality or validate tensor contents.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from moro.config.models import MoroConfig
from moro.core.errors import ExportError
from moro.core.hashing import sha256_text
from moro.storage import db


@dataclass(frozen=True)
class ExportRun:
    id: str
    directory: Path
    config: MoroConfig

    @property
    def adapter_path(self) -> Path:
        return self.directory / "adapter"


def validate_adapter(directory: Path) -> None:
    """Require the unsharded LoRA layout produced by the current trainer."""
    if not directory.is_dir():
        raise ExportError(f"Adapter directory not found: {directory}")
    if directory.is_symlink() or any(p.is_symlink() for p in directory.rglob("*")):
        raise ExportError("Adapter must contain materialized files, not symbolic links.")
    try:
        metadata = json.loads((directory / "adapter_config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ExportError(f"Cannot read adapter_config.json: {exc}") from exc
    if not isinstance(metadata, dict) or metadata.get("peft_type") != "LORA":
        raise ExportError("adapter_config.json must describe a LORA adapter.")
    rank = metadata.get("r")
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ExportError("Adapter configuration must contain a positive integer rank (r).")
    weights = [directory / name for name in ("adapter_model.safetensors", "adapter_model.bin")]
    if not any(path.is_file() and path.stat().st_size > 0 for path in weights):
        raise ExportError(
            "Adapter weights are missing or empty; expected adapter_model.safetensors/bin."
        )


def resolve_export_run(root: Path, project_name: str, run_id: str | None) -> ExportRun:
    """Resolve only this project's completed runs and verify saved configuration."""
    conn = db.get_connection(root)
    try:
        project = conn.execute("SELECT id FROM projects WHERE name = ?", (project_name,)).fetchone()
        if project is None:
            raise ExportError("No recorded project found. Train a model before exporting.")
        if run_id:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ? AND project_id = ?", (run_id, project["id"])
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM runs WHERE project_id = ? AND status = 'completed' "
                "ORDER BY created_at DESC, id DESC LIMIT 1",
                (project["id"],),
            ).fetchone()
        if row is None:
            raise ExportError("No matching completed run found in this project.")
        if row["status"] != "completed":
            raise ExportError(
                f"Run {row['id']} is {row['status']}; export requires a completed run."
            )
    finally:
        conn.close()

    directory = Path(row["output_dir"])
    if not directory.is_absolute():
        directory = root / directory
    try:
        raw_config = (directory / "config.json").read_text("utf-8")
        config = MoroConfig.model_validate_json(raw_config)
    except (OSError, ValueError, ValidationError) as exc:
        raise ExportError(f"Run configuration snapshot is missing or invalid: {exc}") from exc
    if (
        sha256_text(json.dumps(json.loads(raw_config), ensure_ascii=False, separators=(",", ":")))
        != row["config_hash"]
    ):
        raise ExportError("Run configuration snapshot does not match its recorded hash.")
    if config.model.name != row["model_name"] or config.model.quantization != row["quantization"]:
        raise ExportError("Run model identity conflicts with its configuration snapshot.")
    if not config.model.name.strip():
        raise ExportError("Run configuration snapshot has an empty model name.")
    result = ExportRun(row["id"], directory, config)
    validate_adapter(result.adapter_path)
    return result
