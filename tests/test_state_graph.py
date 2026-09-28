"""Unit tests for the Unified State Graph Lineage Manager."""

from pathlib import Path

from moro.storage.state_graph import StateGraphManager


def test_state_graph_lineage_flow(tmp_path: Path):
    db_file = tmp_path / "state_graph.db"
    manager = StateGraphManager(db_file)

    # 1. Record raw source
    manager.record_node(
        "raw_support_001", "raw_source", name="support_v1.jsonl", metadata={"rows": 100}
    )

    # 2. Record dataset version
    manager.record_node(
        "ds_ver_001",
        "dataset_version",
        parent_id="raw_support_001",
        name="clean_train_v1",
        metadata={"train_split": 80},
    )

    # 3. Record training run
    manager.record_node(
        "run_qwen_lora",
        "training_run",
        parent_id="ds_ver_001",
        name="qwen-lora-v1",
        metadata={"loss": 1.2},
    )

    # 4. Record eval
    manager.record_node(
        "eval_qwen_001",
        "eval_result",
        parent_id="run_qwen_lora",
        name="eval-golden-v1",
        metadata={"pass_rate": 0.98},
    )

    # 5. Record release
    manager.record_node(
        "rel_qwen_prod", "release", parent_id="eval_qwen_001", name="release-prod-v1"
    )

    # Verify Ancestry Trace
    ancestors = manager.get_ancestors("rel_qwen_prod")
    assert len(ancestors) == 5
    assert ancestors[0]["id"] == "raw_support_001"
    assert ancestors[1]["id"] == "ds_ver_001"
    assert ancestors[2]["id"] == "run_qwen_lora"
    assert ancestors[3]["id"] == "eval_qwen_001"
    assert ancestors[4]["id"] == "rel_qwen_prod"

    # Verify Summary counts
    summary = manager.get_summary()
    assert summary["raw_source"] == 1
    assert summary["dataset_version"] == 1
    assert summary["training_run"] == 1
    assert summary["eval_result"] == 1
    assert summary["release"] == 1

    # Verify Full Graph
    graph = manager.get_graph()
    assert len(graph["nodes"]) == 5
    assert len(graph["edges"]) == 4
