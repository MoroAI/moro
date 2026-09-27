"""
Tests for Flywheel Ingestor and Orchestrator.
"""


from moro.flywheel.ingestors.sqlite_ingestor import SQLiteLogIngestor
from moro.flywheel.models import InferenceLogPayload
from moro.flywheel.orchestrator import FlywheelConfig, MoroAIFlywheelOrchestrator
from moro.flywheel.storage.schema import get_db_stats, initialize_production_db


def test_sqlite_ingestor_and_orchestrator_cycle(tmp_path):
    db_path = tmp_path / "prod.db"
    out_dir = tmp_path / "dpo_out"
    initialize_production_db(db_path)

    ingestor = SQLiteLogIngestor(db_path)

    # 1. Insert 3 logs: 1 human correction, 1 negative with context, 1 neutral
    ingestor.insert_log(
        InferenceLogPayload(
            session_id="sess_1",
            prompt="What is X?",
            completion="X is 1",
            human_correction="X is 2",
            user_rating=-0.5,
        )
    )
    ingestor.insert_log(
        InferenceLogPayload(
            session_id="sess_2",
            prompt="What is Y?",
            completion="Y is bad",
            context="Y is actually good and approved.",
            user_rating=-0.9,
        )
    )
    # Neutral log without ratings or correction should not generate preference pairs
    ingestor.insert_log(
        InferenceLogPayload(
            session_id="sess_3",
            prompt="Hello",
            completion="Hi there",
        )
    )

    stats = get_db_stats(db_path)
    assert stats["total_logs"] == 3
    assert stats["pending_logs"] == 3

    # 2. Run orchestrator cycle
    config = FlywheelConfig(output_dir=out_dir, min_pairs_per_epoch=1)
    orchestrator = MoroAIFlywheelOrchestrator(config=config, ingestor=ingestor)

    summary = orchestrator.run_cycle(epoch_id="epoch_test_1")
    assert summary.pairs_generated == 2
    assert summary.logs_ingested == 2  # filtered to logs with signals
    assert summary.dataset_path is not None
    assert summary.dataset_path.exists()

    # 3. Check database updates: preference pairs recorded, epoch recorded
    stats_after = get_db_stats(db_path)
    assert stats_after["total_pairs"] == 2
    assert stats_after["total_epochs"] == 1

    # 4. Verify IDEMPOTENCY: second run finds 0 eligible unprocessed logs
    summary_2 = orchestrator.run_cycle()
    assert summary_2.logs_ingested == 0
    assert summary_2.pairs_generated == 0


def test_ingest_from_jsonl(tmp_path):
    db_path = tmp_path / "prod.db"
    jsonl_file = tmp_path / "chat_logs.jsonl"
    jsonl_file.write_text(
        '{"session_id": "c1", "prompt": "Hi", "completion": "Hello", "user_rating": 1.0}\n'
        '{"session_id": "c2", "prompt": "Dosage?", "completion": "100mg", "human_correction": "50mg"}\n'
    )
    initialize_production_db(db_path)
    ingestor = SQLiteLogIngestor(db_path)
    count = ingestor.insert_logs_from_jsonl(jsonl_file)
    assert count == 2

    pending = ingestor.get_pending_count()
    assert pending == 2
