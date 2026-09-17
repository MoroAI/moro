"""
Export module — adapter copy, manifest generation, model card.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from moro.core.errors import ExportError
from moro.core.hashing import sha256_file
from moro.core.ids import new_id


def export_adapter(run_dir: Path, out_dir: Path) -> Path:
    """
    Stage an independent adapter copy, refusing overlaps and existing exports.

    Publication is a same-filesystem rename. This does not make the surrounding
    manifest/card writes transactional or protect against concurrent source edits.
    """
    try:
        adapter_src = (Path(run_dir) / "adapter").resolve()
        if not adapter_src.is_dir():
            raise ExportError(f"Adapter directory not found: {adapter_src}")

        out_dir = Path(out_dir)
        dest = out_dir / "adapter"
        resolved_dest = dest.resolve()
        if adapter_src.is_relative_to(resolved_dest) or resolved_dest.is_relative_to(adapter_src):
            raise ExportError(
                "Adapter source and export destination overlap; choose another --out."
            )
        if dest.exists() or dest.is_symlink():
            raise ExportError(f"Export destination already exists: {dest}. Choose a fresh --out.")

        # Refuse links rather than following them into unrelated or recursive trees.
        for entry in adapter_src.rglob("*"):
            if entry.is_symlink():
                raise ExportError(f"Adapter contains a symbolic link: {entry}")

        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".moro-export-", dir=out_dir) as staging:
            staged_adapter = Path(staging) / "adapter"
            shutil.copytree(adapter_src, staged_adapter, symlinks=True)
            # Also catch links introduced while copying; never publish a linked bundle.
            if any(entry.is_symlink() for entry in staged_adapter.rglob("*")):
                raise ExportError("Adapter contains a symbolic link introduced during export.")
            if dest.exists() or dest.is_symlink():
                raise ExportError(
                    f"Export destination already exists: {dest}. Choose a fresh --out."
                )
            staged_adapter.rename(dest)
        return dest
    except (OSError, RuntimeError) as exc:
        raise ExportError(f"Could not export adapter: {exc}") from exc


def generate_manifest(
    project_name: str,
    run_id: str,
    base_model: str,
    artifact_paths: list[Path],
    eval_summary: dict | None = None,
    dataset_version_id: str | None = None,
    base_model_revision: str | None = None,
) -> dict:
    """
    Generate a release manifest dict.
    """
    artifacts = []
    for path in artifact_paths:
        path = Path(path)
        artifacts.append(
            {
                "type": path.name if path.is_file() else path.stem,
                "path": str(path),
                "sha256": sha256_file(path) if path.is_file() else None,
                "size_bytes": path.stat().st_size if path.is_file() else None,
            }
        )

    return {
        "release_id": new_id("rel"),
        "project_name": project_name,
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_model": base_model,
        "base_model_revision": base_model_revision,
        "dataset_version_id": dataset_version_id,
        "eval_summary": eval_summary or {},
        "artifacts": artifacts,
    }


def write_manifest(manifest: dict, out_dir: Path) -> Path:
    """Write manifest.json to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def generate_model_card(
    project_name: str,
    model_name: str,
    run_id: str,
    eval_summary: dict | None = None,
    dataset_stats: dict | None = None,
) -> str:
    """Generate a minimal model card in Markdown."""
    lines = [
        f"# {project_name} — Model Card",
        "",
        f"**Base model:** `{model_name}`  ",
        f"**Run ID:** `{run_id}`  ",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Training",
        "",
        f"This model was fine-tuned from `{model_name}` using MoroAI.",
        "",
    ]

    if dataset_stats:
        lines += [
            "## Dataset",
            "",
            f"- Total rows: {dataset_stats.get('rows_valid', 'N/A')}",
            f"- Avg token count: {dataset_stats.get('avg_tokens', 'N/A')}",
            "",
        ]

    if eval_summary:
        lines += [
            "## Evaluation",
            "",
            f"- Pass rate: {eval_summary.get('pass_rate', 'N/A')}",
            f"- Avg score: {eval_summary.get('avg_score', 'N/A')}",
            "",
        ]

    lines += [
        "## Usage",
        "",
        "```python",
        "from transformers import AutoModelForCausalLM, AutoTokenizer",
        "from peft import PeftModel",
        "",
        f'base = AutoModelForCausalLM.from_pretrained("{model_name}")',
        'model = PeftModel.from_pretrained(base, "./adapter")',
        f'tokenizer = AutoTokenizer.from_pretrained("{model_name}")',
        "```",
        "",
        "## License",
        "",
        "See base model license.",
    ]

    return "\n".join(lines)


def write_model_card(content: str, out_dir: Path) -> Path:
    """Write model_card.md to out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "model_card.md"
    path.write_text(content, encoding="utf-8")
    return path
