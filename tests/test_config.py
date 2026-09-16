"""Tests for config models and loader."""

from pathlib import Path

import pytest

from moro.config.models import (
    AdapterConfig,
    DatasetConfig,
    ModelConfig,
    ProjectConfig,
    TrainingConfig,
)
from moro.core.errors import ConfigError


def test_project_config_valid():
    cfg = ProjectConfig(name="my-project")
    assert cfg.name == "my-project"
    assert cfg.privacy_mode == "local_only"
    assert cfg.seed == 42


def test_project_config_invalid_empty_name():
    with pytest.raises(Exception):
        ProjectConfig(name="")


def test_dataset_config_defaults():
    cfg = DatasetConfig(source=Path("./data/raw/test.jsonl"))
    assert cfg.format == "auto"
    assert cfg.deduplicate is True
    assert cfg.max_seq_length == 1024
    assert cfg.validation_ratio == 0.1
    assert cfg.eval_ratio == 0.1


def test_model_config_defaults():
    cfg = ModelConfig(name="Qwen/Qwen2.5-1.5B-Instruct")
    assert cfg.quantization == "nf4"
    assert cfg.trust_remote_code is False


def test_adapter_config_defaults():
    cfg = AdapterConfig()
    assert cfg.type == "lora"
    assert cfg.r == 16
    assert cfg.alpha == 32
    assert cfg.dropout == 0.05


def test_training_config_defaults():
    cfg = TrainingConfig()
    assert cfg.batch_size == 1
    assert cfg.gradient_accumulation_steps == 16
    assert cfg.optimizer == "paged_adamw_8bit"
    assert cfg.gradient_checkpointing is True


def test_load_config_valid(tmp_project: Path):
    from moro.config.loader import load_config

    cfg = load_config(tmp_project / "moro.yaml")
    assert cfg.project.name == "test-project"
    assert cfg.model.name == "Qwen/Qwen2.5-1.5B-Instruct"


def test_load_config_missing(tmp_path: Path):
    from moro.config.loader import load_config

    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_config_bad_yaml(tmp_path: Path):
    from moro.config.loader import load_config

    bad = tmp_path / "moro.yaml"
    bad.write_text("project: [this is bad yaml: {", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(bad)
