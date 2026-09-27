"""
Tests for MoroAI Flywheel CLI commands.
"""

from typer.testing import CliRunner

from moro.main import app

runner = CliRunner()


def test_flywheel_cli_flow(tmp_path):
    db_file = tmp_path / "prod.db"
    out_dir = tmp_path / "dpo_dataset"

    # 1. Status on empty db
    res = runner.invoke(app, ["flywheel", "status", "--db", str(db_file)])
    assert res.exit_code == 0
    assert "MoroAI DPO Flywheel Status" in res.stdout
    assert "Pending Unprocessed Logs: 0" in res.stdout

    # 2. Ingest JSONL logs
    jsonl = tmp_path / "input.jsonl"
    jsonl.write_text(
        '{"session_id": "s1", "prompt": "Question 1", "completion": "Bad answer", "human_correction": "Good answer"}\n'
        '{"session_id": "s2", "prompt": "Question 2", "completion": "Great answer", "user_rating": 1.0}\n'
    )
    res_ingest = runner.invoke(app, ["flywheel", "ingest", str(jsonl), "--db", str(db_file)])
    assert res_ingest.exit_code == 0
    assert "Ingested 2 production logs" in res_ingest.stdout

    # 3. Status shows 2 pending
    res_status = runner.invoke(app, ["flywheel", "status", "--db", str(db_file)])
    assert "Pending Unprocessed Logs: 2" in res_status.stdout

    # 4. Run flywheel cycle
    res_run = runner.invoke(
        app,
        ["flywheel", "run", "--db", str(db_file), "--output-dir", str(out_dir), "--min-pairs", "1"],
    )
    assert res_run.exit_code == 0
    assert "DPO Flywheel Cycle Completed" in res_run.stdout
    assert "Preference Pairs Generated: 2" in res_run.stdout

    # 5. History command shows completed epoch
    res_hist = runner.invoke(app, ["flywheel", "history", "--db", str(db_file)])
    assert res_hist.exit_code == 0
    assert "completed" in res_hist.stdout
