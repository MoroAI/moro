"""Create governed release bundles from recorded runs and evaluation evidence."""

from __future__ import annotations

import asyncio
import fcntl
import os
import tempfile
from pathlib import Path

from moro.config.loader import load_config
from moro.core.errors import ExportError
from moro.core.hashing import sha256_directory
from moro.export.eligibility import resolve_export_run
from moro.export.gates import check_release_requirements
from moro.export.manifest import export_adapter, generate_manifest, write_manifest
from moro.export.paths import deployment_directory


class ReleaseManager:
    def __init__(self, project_root: Path, state_manager=None):
        self.project_root = Path(project_root).resolve()
        self.state_manager = state_manager

    def create_release(self, run_id, version, eval_results=None):
        # Caller-supplied scores are never release evidence. The gate reads the DB
        # and checks the recorded suite and current adapter content hashes.
        cfg = load_config(self.project_root / "moro.yaml")
        selected = resolve_export_run(self.project_root, cfg.project.name, run_id)
        gate = check_release_requirements(self.project_root, selected, cfg)
        destination = deployment_directory(self.project_root, selected.id, version)
        destination.parent.mkdir(parents=True, exist_ok=True)
        lock = os.open(
            destination.parent / ".release.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if destination.exists() or destination.is_symlink():
                raise ExportError("Release version already exists; choose a new version")
            with tempfile.TemporaryDirectory(
                prefix=".release-", dir=destination.parent
            ) as temporary:
                staged = Path(temporary) / "bundle"
                adapter = export_adapter(selected.directory, staged)
                if sha256_directory(adapter) != gate["adapter_sha256"]:
                    raise ExportError("Adapter changed after release gate; release not published")
                manifest = generate_manifest(
                    cfg.project.name,
                    selected.id,
                    selected.config.model.name,
                    sorted(p for p in adapter.rglob("*") if p.is_file()),
                    eval_summary={
                        "gate_status": gate["status"],
                        "evaluations": gate["evaluations"],
                    },
                    dataset_version_id=selected.dataset_version_id,
                    base_model_revision=selected.config.model.revision,
                )
                for artifact in manifest["artifacts"]:
                    artifact["path"] = str(Path(artifact["path"]).relative_to(staged))
                manifest.update(version=version, release_gate=gate)
                write_manifest(manifest, staged)
                staged.rename(destination)
        finally:
            os.close(lock)
        return {
            "release_id": manifest["release_id"],
            "version": version,
            "release_dir": str(destination),
            "manifest_path": str(destination / "manifest.json"),
            "status": "created",
        }

    async def create_release_async(
        self, training_run_id, eval_results=None, version=None, progress_callback=None
    ):
        if progress_callback:
            progress_callback("Verifying recorded release evidence", None)
        result = await asyncio.to_thread(
            self.create_release, training_run_id, version or "v1.0.0", eval_results
        )
        if progress_callback:
            progress_callback("Release bundle created", 100.0)
        return result
