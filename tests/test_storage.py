"""Tests for storage DB layer."""

from pathlib import Path

import pytest

from moro.storage import db as storage_db


def test_get_connection_creates_db(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    assert conn is not None
    db_file = tmp_path / ".moro" / "db.sqlite"
    assert db_file.exists()
    conn.close()


def test_create_project(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    project_id = storage_db.get_or_create_project(conn, "test-project")
    assert project_id.startswith("proj_")

    # Same name returns same ID
    project_id_2 = storage_db.get_or_create_project(conn, "test-project")
    assert project_id == project_id_2
    conn.close()


def test_create_dataset_source(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    pid = storage_db.get_or_create_project(conn, "test")

    src_id = storage_db.get_or_create_dataset_source(
        conn=conn,
        project_id=pid,
        name="support.jsonl",
        source_type="jsonl",
        path="/data/raw/support.jsonl",
        sha256="abc123",
    )
    assert src_id.startswith("src_")
    conn.close()


def test_create_run(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    pid = storage_db.get_or_create_project(conn, "test")

    run_id = storage_db.create_run(
        conn=conn,
        project_id=pid,
        config_hash="hash123",
        model_name="Qwen/Qwen2.5-1.5B-Instruct",
        quantization="nf4",
        output_dir="/runs/test",
    )
    assert run_id.startswith("run_")

    row = storage_db.get_latest_run(conn, pid)
    assert row is not None
    assert row["id"] == run_id
    assert row["status"] == "pending"
    conn.close()


def test_update_run_status(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    pid = storage_db.get_or_create_project(conn, "test")
    run_id = storage_db.create_run(conn, pid, "hash", "model", "nf4", "/out")
    storage_db.update_run_status(conn, run_id, "completed", train_loss=0.15)

    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "completed"
    assert row["train_loss"] == pytest.approx(0.15, abs=0.001)
    conn.close()


def test_add_eval_run(tmp_path: Path):
    conn = storage_db.get_connection(tmp_path)
    eval_id = storage_db.add_eval_run(
        conn=conn,
        run_id=None,
        suite_name="support-golden-v1",
        model="Qwen/Qwen2.5-1.5B-Instruct",
        total_cases=10,
        pass_rate=0.9,
        avg_score=0.87,
        result={"cases": []},
    )
    assert eval_id.startswith("eval_")
    conn.close()
