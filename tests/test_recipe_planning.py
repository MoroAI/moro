import json

import pytest
import yaml
from test_recipe_engine import _make_hardware
from typer.testing import CliRunner

from moro.config.models import MoroConfig
from moro.main import app
from moro.recipes.engine import suggest_recipe
from moro.recipes.rules import estimate_memory, infer_parameter_billions


@pytest.mark.parametrize(
    "name,size",
    [
        ("Qwen/Qwen2.5-1.5B-Instruct", 1.5),
        ("owner/Model-70B", 70),
        ("owner/Model-13B", 13),
        ("owner/model-500M", 0.5),
        ("70B-owner/custom-model", None),
        ("owner/mini-custom", None),
    ],
)
def test_model_size_is_not_capped_or_guessed(name, size):
    assert infer_parameter_billions(name)[0] == size


def test_metadata_takes_precedence(tmp_path):
    model = tmp_path / "misleading-1B"
    model.mkdir()
    (model / "config.json").write_text(json.dumps({"num_parameters": 70000000000}))
    assert infer_parameter_billions(str(model)) == (70, "local_config")
    (model / "config.json").write_text("not json")
    assert infer_parameter_billions(str(model)) == (1, "model_name")


def test_unknown_model_has_no_fabricated_estimate():
    recipe = suggest_recipe(_make_hardware(24), model_name="private/custom")
    assert recipe.model == "private/custom"
    assert recipe.estimated_vram_gb is None
    assert recipe.fit == "unknown"
    assert recipe.confidence == "low"


def test_oversized_model_is_preserved_and_rejected_by_estimate():
    recipe = suggest_recipe(_make_hardware(4), model_name="private/model-70B")
    assert recipe.model == "private/model-70B"
    assert recipe.parameter_billions == 70
    assert recipe.fit == "over_budget"
    assert recipe.estimated_vram_gb > 4
    assert recipe.confidence == "low"


def test_memory_grows_with_settings():
    settings = dict(
        quantization="nf4",
        precision="auto",
        sequence_length=512,
        batch_size=1,
        rank=8,
        module_count=4,
        checkpointing=True,
        optimizer="paged_adamw_8bit",
    )
    base = sum(estimate_memory(3, **settings).values())
    for change in [
        dict(sequence_length=2048),
        dict(batch_size=4),
        dict(rank=32),
        dict(module_count=7),
        dict(checkpointing=False),
        dict(quantization="none"),
    ]:
        assert sum(estimate_memory(3, **(settings | change)).values()) > base


def test_config_defaults_and_overrides():
    cfg = MoroConfig.model_validate(
        dict(
            project=dict(name="test"),
            dataset=dict(source="data/raw", max_seq_length=512),
            model=dict(name="Qwen/model-3B", quantization="int8"),
            adapter=dict(r=8, alpha=16, target_modules=["q_proj"]),
            training=dict(batch_size=2, gradient_accumulation_steps=4, optimizer="adamw_torch"),
        )
    )
    recipe = suggest_recipe(_make_hardware(24), config=cfg)
    assert recipe.model == cfg.model.name
    assert recipe.max_seq_length == 512
    assert recipe.quantization == "int8"
    assert recipe.batch_size == 2
    assert recipe.target_modules == ["q_proj"]
    assert recipe.config_patch["adapter"]["r"] == 8
    override = suggest_recipe(
        _make_hardware(24), config=cfg, model_name="custom/70B", max_seq_length=1024
    )
    assert override.model == "custom/70B"
    assert override.max_seq_length == 1024


def test_cli_project_config_and_patch_are_read_only(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project)
    monkeypatch.setattr("moro.cli.recipe.detect_hardware", lambda: _make_hardware(24).model_dump())
    config_file = tmp_project / "moro.yaml"
    before = config_file.read_bytes()
    runner = CliRunner()
    result = runner.invoke(app, ["recipe", "suggest", "--json"])
    assert result.exit_code == 0, result.output
    result_json = json.loads(result.output)
    assert result_json["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    result = runner.invoke(app, ["recipe", "suggest", "--yaml-patch"])
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(result.output) == result_json["config_patch"]
    assert config_file.read_bytes() == before
    result = runner.invoke(app, ["recipe", "suggest", "--json", "--yaml-patch"])
    assert result.exit_code == 2


def test_explicit_config_and_model_precedence(tmp_project, monkeypatch):
    monkeypatch.chdir(tmp_project.parent)
    monkeypatch.setattr("moro.cli.recipe.detect_hardware", lambda: _make_hardware(24).model_dump())
    result = CliRunner().invoke(
        app,
        [
            "recipe",
            "suggest",
            "--config",
            str(tmp_project / "moro.yaml"),
            "--model",
            "private/70B",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["model"] == "private/70B"


def test_invalid_config_is_not_silently_ignored(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "broken.yaml"
    cfg.write_text("model: [")
    result = CliRunner().invoke(app, ["recipe", "suggest", "--config", str(cfg)])
    assert result.exit_code == 2


def test_standalone_unknown_model_renders_table(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("moro.cli.recipe.detect_hardware", lambda: _make_hardware(8).model_dump())
    result = CliRunner().invoke(app, ["recipe", "suggest", "--model", "private/custom"])
    assert result.exit_code == 0, result.output
    assert "unknown" in result.output


def test_non_cuda_vram_is_not_zero_memory_claim():
    recipe = suggest_recipe(_make_hardware(None, gpu=False))
    assert recipe.estimated_vram_gb is None
    assert recipe.estimated_memory_gb > 0
    assert recipe.fit == "unknown"
