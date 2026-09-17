import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from moro.core.ids import new_id

DB_FILENAME = "db.sqlite"


def utcnow() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def get_db_path(root: Path) -> Path:
    return Path(root) / ".moro" / DB_FILENAME


def get_connection(root: Path) -> sqlite3.Connection:
    """Open (or create) the project SQLite database and return a connection."""
    db_path = get_db_path(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they do not already exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            privacy_mode TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS dataset_sources (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            imported_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS dataset_versions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            version TEXT NOT NULL,
            normalized_path TEXT NOT NULL,
            stats_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id),
            FOREIGN KEY(source_id) REFERENCES dataset_sources(id)
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            dataset_version_id TEXT,
            run_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            config_hash TEXT NOT NULL,
            model_name TEXT NOT NULL,
            quantization TEXT NOT NULL,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            peak_vram_gb REAL,
            tokens_per_sec REAL,
            train_loss REAL,
            validation_loss REAL,
            output_dir TEXT NOT NULL,
            error TEXT,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        );

        CREATE TABLE IF NOT EXISTS eval_runs (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            suite_name TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL,
            total_cases INTEGER NOT NULL,
            pass_rate REAL NOT NULL,
            avg_score REAL NOT NULL,
            result_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            sha256 TEXT,
            size_bytes INTEGER,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------


def get_or_create_project(
    conn: sqlite3.Connection,
    name: str,
    privacy_mode: str = "local_only",
) -> str:
    row = conn.execute("SELECT id FROM projects WHERE name = ?", (name,)).fetchone()

    if row:
        return row["id"]

    project_id = new_id("proj")
    conn.execute(
        "INSERT INTO projects (id, name, privacy_mode, created_at) VALUES (?, ?, ?, ?)",
        (project_id, name, privacy_mode, utcnow()),
    )
    conn.commit()
    return project_id


# ---------------------------------------------------------------------------
# Dataset source helpers
# ---------------------------------------------------------------------------


def get_or_create_dataset_source(
    conn: sqlite3.Connection,
    project_id: str,
    name: str,
    source_type: str,
    path: str,
    sha256: str,
) -> str:
    row = conn.execute(
        "SELECT id FROM dataset_sources WHERE project_id = ? AND path = ?",
        (project_id, path),
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE dataset_sources SET sha256 = ?, name = ?, source_type = ? WHERE id = ?",
            (sha256, name, source_type, row["id"]),
        )
        conn.commit()
        return row["id"]

    source_id = new_id("src")
    conn.execute(
        """
        INSERT INTO dataset_sources (id, project_id, name, source_type, path, sha256, imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source_id, project_id, name, source_type, path, sha256, utcnow()),
    )
    conn.commit()
    return source_id


# ---------------------------------------------------------------------------
# Dataset version helpers
# ---------------------------------------------------------------------------


def add_dataset_version(
    conn: sqlite3.Connection,
    project_id: str,
    source_id: str,
    version: str,
    normalized_path: str,
    stats: dict,
) -> str:
    version_id = new_id("ds")
    conn.execute(
        """
        INSERT INTO dataset_versions
            (id, project_id, source_id, version, normalized_path, stats_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            version_id,
            project_id,
            source_id,
            version,
            normalized_path,
            json.dumps(stats, ensure_ascii=False),
            utcnow(),
        ),
    )
    conn.commit()
    return version_id


def get_latest_dataset_version(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM dataset_versions WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()


# ---------------------------------------------------------------------------
# Run helpers
# ---------------------------------------------------------------------------


def create_run(
    conn: sqlite3.Connection,
    project_id: str,
    config_hash: str,
    model_name: str,
    quantization: str,
    output_dir: str,
    run_name: str | None = None,
    dataset_version_id: str | None = None,
) -> str:
    run_id = new_id("run")
    conn.execute(
        """
        INSERT INTO runs
            (id, project_id, dataset_version_id, run_name, status,
             config_hash, model_name, quantization, created_at, output_dir)
        VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            project_id,
            dataset_version_id,
            run_name,
            config_hash,
            model_name,
            quantization,
            utcnow(),
            output_dir,
        ),
    )
    conn.commit()
    return run_id


def update_run_status(
    conn: sqlite3.Connection,
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    train_loss: float | None = None,
    validation_loss: float | None = None,
    peak_vram_gb: float | None = None,
    tokens_per_sec: float | None = None,
) -> None:
    finished_at = utcnow() if status in ("completed", "failed", "cancelled") else None
    conn.execute(
        """
        UPDATE runs SET
            status = ?,
            finished_at = COALESCE(?, finished_at),
            error = COALESCE(?, error),
            train_loss = COALESCE(?, train_loss),
            validation_loss = COALESCE(?, validation_loss),
            peak_vram_gb = COALESCE(?, peak_vram_gb),
            tokens_per_sec = COALESCE(?, tokens_per_sec)
        WHERE id = ?
        """,
        (
            status,
            finished_at,
            error,
            train_loss,
            validation_loss,
            peak_vram_gb,
            tokens_per_sec,
            run_id,
        ),
    )
    conn.commit()


def get_latest_run(conn: sqlite3.Connection, project_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
        (project_id,),
    ).fetchone()


def list_runs(conn: sqlite3.Connection, project_id: str, limit: int = 20) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
        (project_id, limit),
    ).fetchall()


# ---------------------------------------------------------------------------
# Eval run helpers
# ---------------------------------------------------------------------------


def add_eval_run(
    conn: sqlite3.Connection,
    run_id: str | None,
    suite_name: str,
    model: str,
    total_cases: int,
    pass_rate: float,
    avg_score: float,
    result: dict,
) -> str:
    eval_id = result.get("id") or new_id("eval")
    result = {**result, "id": eval_id}
    conn.execute(
        """
        INSERT INTO eval_runs
            (id, run_id, suite_name, model, created_at, total_cases,
             pass_rate, avg_score, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eval_id,
            run_id,
            suite_name,
            model,
            utcnow(),
            total_cases,
            pass_rate,
            avg_score,
            json.dumps(result, ensure_ascii=False),
        ),
    )
    conn.commit()
    return eval_id


# ---------------------------------------------------------------------------
# Artifact helpers
# ---------------------------------------------------------------------------


def add_artifact(
    conn: sqlite3.Connection,
    run_id: str,
    artifact_type: str,
    path: str,
    sha256: str | None = None,
    size_bytes: int | None = None,
) -> str:
    artifact_id = new_id("art")
    conn.execute(
        """
        INSERT INTO artifacts (id, run_id, type, path, sha256, size_bytes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (artifact_id, run_id, artifact_type, path, sha256, size_bytes, utcnow()),
    )
    conn.commit()
    return artifact_id
