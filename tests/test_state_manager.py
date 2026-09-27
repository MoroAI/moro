"""Unit tests for the MoroAI Unified State Manager."""

from pathlib import Path

from moro.state.manager import StateManager
from moro.state.schema import EdgeType, NodeStatus, NodeType, initialize_state_db


def test_initialize_state_db_idempotent(tmp_path: Path):
    db_file = tmp_path / "state.db"
    conn1 = initialize_state_db(db_file)
    conn1.close()
    assert db_file.exists()

    # Second initialization should succeed idempotently
    conn2 = initialize_state_db(db_file)
    conn2.close()


def test_state_manager_node_and_edge_crud(tmp_path: Path):
    db_file = tmp_path / "state.db"
    manager = StateManager(db_file)

    # 1. Create nodes
    raw_id = manager.create_node(
        node_type=NodeType.RAW_SOURCE,
        name="raw_input.jsonl",
        payload={"size_bytes": 1024},
        status=NodeStatus.ACTIVE,
    )
    assert raw_id.startswith("raw_")

    ds_id = manager.create_node(
        node_type=NodeType.DATASET_VERSION,
        name="clean_v1.jsonl",
        payload={"samples": 100},
        status=NodeStatus.COMPLETED,
        parent_node_id=raw_id,
    )
    assert ds_id.startswith("data")

    # 2. Get node
    raw_node = manager.get_node(raw_id)
    assert raw_node is not None
    assert raw_node["name"] == "raw_input.jsonl"
    assert raw_node["status"] == "active"

    # 3. Update node
    updated = manager.update_node(raw_id, status=NodeStatus.COMPLETED)
    assert updated is True
    assert manager.get_node(raw_id)["status"] == "completed"

    # 4. Create edge
    edge_id = manager.create_edge(
        source_node_id=raw_id,
        target_node_id=ds_id,
        edge_type=EdgeType.DERIVED_FROM,
        metadata={"step": "ppmi_filter"},
    )
    assert edge_id.startswith("edge_")

    # 5. Connected nodes
    children = manager.get_connected_nodes(raw_id, direction="outgoing")
    assert len(children) == 1
    assert children[0]["node_id"] == ds_id

    parents = manager.get_connected_nodes(ds_id, direction="incoming")
    assert len(parents) == 1
    assert parents[0]["node_id"] == raw_id


def test_state_manager_lineage_tracing(tmp_path: Path):
    db_file = tmp_path / "state.db"
    manager = StateManager(db_file)

    raw_id = manager.create_node(NodeType.RAW_SOURCE, "raw.jsonl")
    ds_id = manager.create_node(NodeType.DATASET_VERSION, "ds_v1")
    run_id = manager.create_node(NodeType.TRAINING_RUN, "run_01")
    rel_id = manager.create_node(NodeType.RELEASE, "rel_v1")
    dep_id = manager.create_node(NodeType.DEPLOYMENT, "dep_ollama")

    manager.create_edge(raw_id, ds_id, EdgeType.DERIVED_FROM)
    manager.create_edge(ds_id, run_id, EdgeType.TRAINED_ON)
    manager.create_edge(run_id, rel_id, EdgeType.RELEASED_FROM)
    manager.create_edge(rel_id, dep_id, EdgeType.DEPLOYED_FROM)

    lineage = manager.trace_lineage(dep_id)
    assert lineage["node_id"] == dep_id
    assert len(lineage["ancestors"]) > 0


def test_state_manager_model_registry_and_promotion(tmp_path: Path):
    db_file = tmp_path / "state.db"
    manager = StateManager(db_file)

    model_1 = manager.register_model(
        model_name="qwen-chat",
        version="1.0.0",
        base_model="Qwen/Qwen2.5-1.5B",
        quantization="q4_k_m",
    )
    model_2 = manager.register_model(
        model_name="qwen-chat",
        version="1.1.0",
        base_model="Qwen/Qwen2.5-1.5B",
        quantization="q4_k_m",
    )

    models = manager.list_models()
    assert len(models) == 2

    # Promote model_1 to production
    manager.promote_model_to_production(model_1)
    prod = manager.list_models(production_only=True)
    assert len(prod) == 1
    assert prod[0]["model_id"] == model_1

    # Promote model_2 to production (should demote model_1)
    manager.promote_model_to_production(model_2)
    prod = manager.list_models(production_only=True)
    assert len(prod) == 1
    assert prod[0]["model_id"] == model_2
    assert manager.get_model("qwen-chat", "1.0.0")["is_production"] == 0

    # Operation logs
    logs = manager.get_operation_log()
    assert len(logs) >= 4
