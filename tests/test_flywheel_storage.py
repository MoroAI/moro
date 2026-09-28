"""
Tests for Flywheel SQLite storage schema and operations.
"""

from moro.flywheel.storage.schema import get_db_stats, get_production_db, initialize_production_db


def test_initialize_production_db(tmp_path):
    db_path = tmp_path / "test_logs.db"
    conn = initialize_production_db(db_path)
    assert db_path.exists()

    # Tables should exist
    tables = [
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    ]
    assert "inference_logs" in tables
    assert "preference_pairs" in tables
    assert "dpo_epochs" in tables
    assert "flywheel_state" in tables
    conn.close()


def test_idempotent_db_init(tmp_path):
    db_path = tmp_path / "test_logs.db"
    conn1 = initialize_production_db(db_path)
    conn1.close()

    # Second init should not raise error
    conn2 = get_production_db(db_path)
    stats = get_db_stats(db_path)
    assert stats["total_logs"] == 0
    assert stats["pending_logs"] == 0
    conn2.close()
