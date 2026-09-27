"""Unit tests for the MoroAI Model Registry."""

from pathlib import Path

from moro.registry.manager import ModelRegistry


def test_model_registry_crud(tmp_path: Path):
    db_file = tmp_path / "registry.db"
    reg = ModelRegistry(db_file)

    # 1. Register a model
    reg.register_model(
        model_id="qwen-1.5b-v1",
        name="qwen-quantum-v1",
        run_id="run_123",
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        artifact_path="/tmp/adapter",
        val_loss=1.05,
        pass_rate=0.98,
        tag="candidate",
    )

    # 2. List
    models = reg.list_models()
    assert len(models) == 1
    assert models[0]["model_id"] == "qwen-1.5b-v1"
    assert models[0]["tag"] == "candidate"

    # 3. Promote
    promoted = reg.promote_model("qwen-1.5b-v1", "production")
    assert promoted is True

    m = reg.get_model("qwen-1.5b-v1")
    assert m is not None
    assert m["tag"] == "production"

    # 4. Filter by tag
    prod_models = reg.list_models(tag="production")
    assert len(prod_models) == 1

    cand_models = reg.list_models(tag="candidate")
    assert len(cand_models) == 0

    # 5. Delete
    deleted = reg.delete_model("qwen-1.5b-v1")
    assert deleted is True
    assert len(reg.list_models()) == 0
