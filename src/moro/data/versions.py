"""Publish immutable dataset directories and verify their complete file inventories."""

import json
import tempfile
from pathlib import Path
from uuid import uuid4

from moro.config.models import MoroConfig
from moro.core.errors import DatasetError
from moro.core.hashing import config_snapshot_hash, sha256_directory, sha256_file
from moro.data.splitter import write_split
from moro.storage import db


def source_fingerprint(source: Path) -> str:
    source = source.resolve()
    return sha256_directory(source) if source.is_dir() else sha256_file(source)


def build_key(config: MoroConfig, source: Path, fingerprint: str, limit: int | None) -> str:
    return config_snapshot_hash(
        json.dumps(
            {
                "compiler": 1,
                "dataset": config.dataset.model_dump(mode="json"),
                "source": str(source.resolve()),
                "sha256": fingerprint,
                "seed": config.project.seed,
                "limit": limit,
            }
        )
    )


def verify_snapshot(root: Path, row) -> dict:
    path = root / row["manifest_path"]
    try:
        if path.is_symlink() or sha256_file(path) != row["manifest_sha256"]:
            raise DatasetError("Dataset manifest integrity failure. Rebuild with --force.")
        manifest = json.loads(path.read_text())
        if manifest["dataset_version_id"] != row["version_id"]:
            raise DatasetError("Dataset version identity mismatch.")
        for name, digest in manifest["files"].items():
            file = path.parent / name
            if file.is_symlink() or not file.resolve().is_relative_to(path.parent.resolve()):
                raise DatasetError("Unsafe dataset artifact path.")
            if sha256_file(file) != digest:
                raise DatasetError(f"Dataset integrity failure: {name}. Rebuild with --force.")
        return manifest
    except (OSError, ValueError, KeyError) as exc:
        raise DatasetError(f"Dataset snapshot is unavailable or invalid: {exc}") from exc


def select_snapshot(root: Path, config: MoroConfig, limit: int | None = None):
    source = config.dataset.source
    source = source if source.is_absolute() else root / source
    try:
        fingerprint = source_fingerprint(source)
    except (OSError, ValueError) as exc:
        raise DatasetError(f"Cannot fingerprint dataset source: {exc}") from exc
    key = build_key(config, source, fingerprint, limit)
    conn = db.get_connection(root)
    try:
        row = conn.execute(
            """SELECT s.* FROM dataset_snapshots s
            JOIN dataset_versions v ON v.id=s.version_id
            JOIN projects p ON p.id=v.project_id
            WHERE p.name=? AND s.build_key=? ORDER BY v.created_at DESC, v.id DESC LIMIT 1""",
            (config.project.name, key),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return row, verify_snapshot(root, row)
    return None


def publish_snapshot(root, config, source, fingerprint, limit, rows, splits, stats, rejected):
    version_id = "ds_" + uuid4().hex
    versions = root / "data" / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    destination = versions / version_id
    conn = db.get_connection(root)
    try:
        project_id = db.get_or_create_project(
            conn, config.project.name, config.project.privacy_mode
        )
        source_id = db.get_or_create_dataset_source(
            conn, project_id, source.name, config.dataset.format, str(source.resolve()), fingerprint
        )
        with tempfile.TemporaryDirectory(prefix=".build-", dir=versions) as temporary:
            stage = Path(temporary) / "snapshot"
            stage.mkdir()
            write_split(rows, stage / "dataset.jsonl")
            for name, items in zip(("train", "validation", "eval"), splits):
                write_split(items, stage / f"{name}.jsonl")
            (stage / "report.json").write_text(stats.model_dump_json(indent=2))
            # Reasons and locations only; do not duplicate rejected private contents.
            (stage / "rejections.jsonl").write_text(
                "".join(item.model_dump_json(exclude={"raw"}) + "\n" for item in rejected)
            )
            manifest = {
                "schema_version": 1,
                "dataset_version_id": version_id,
                "source": str(source.resolve()),
                "source_sha256": fingerprint,
                "build_key": build_key(config, source, fingerprint, limit),
                "dataset": config.dataset.model_dump(mode="json"),
                "seed": config.project.seed,
                "limit": limit,
                "files": {p.name: sha256_file(p) for p in stage.iterdir()},
            }
            manifest_path = stage / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
            if source_fingerprint(source) != fingerprint:
                raise DatasetError("Dataset source changed during build; retry with stable inputs.")
            digest = sha256_file(manifest_path)
            # Unique destinations avoid shared split files and count-based version races.
            stage.rename(destination)
            try:
                with conn:
                    conn.execute(
                        """INSERT INTO dataset_versions
                        (id, project_id, source_id, version, normalized_path, stats_json, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            version_id,
                            project_id,
                            source_id,
                            version_id,
                            str((destination / "dataset.jsonl").relative_to(root)),
                            stats.model_dump_json(),
                            db.utcnow(),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO dataset_snapshots VALUES (?, ?, ?, ?)",
                        (
                            version_id,
                            manifest["build_key"],
                            str((destination / "manifest.json").relative_to(root)),
                            digest,
                        ),
                    )
            except Exception:
                # Keep unregistered files for inspection after a failed database commit.
                raise DatasetError(
                    f"Dataset files preserved at {destination}; registration failed."
                )
        return destination, manifest
    finally:
        conn.close()
