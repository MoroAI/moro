"""Unit tests for the Pre-Flight Validation Engine."""

from pathlib import Path

import yaml

from moro.config.loader import load_config
from moro.validation.engine import validate_project


def test_validation_engine_healthy(tmp_path: Path):
    cfg_data = {
        "project": {"name": "test_proj", "privacy_mode": "local_only"},
        "dataset": {
            "source": "./data/raw/data.jsonl",
            "max_seq_length": 512,
            "validation_ratio": 0.1,
            "eval_ratio": 0.1,
        },
        "model": {"name": "Qwen/Qwen2.5-0.5B-Instruct", "quantization": "none"},
        "adapter": {"r": 8, "alpha": 16},
        "training": {
            "batch_size": 1,
            "gradient_accumulation_steps": 16,
            "optimizer": "adamw_torch",
            "gradient_checkpointing": True,
            "precision": "fp32",
        },
        "eval": {"suites": [{"path": "./eval/test_eval.yaml"}]},
        "release": {"require": {"safety_pass": True}},
    }
    cfg_file = tmp_path / "moro.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg_data))

    # Create dummy dataset and eval suite
    (tmp_path / "data" / "raw").mkdir(parents=True)
    (tmp_path / "data" / "raw" / "data.jsonl").write_text('{"messages": []}\n')

    (tmp_path / "eval").mkdir(parents=True)
    (tmp_path / "eval" / "test_eval.yaml").write_text(yaml.safe_dump({"name": "test_suite", "cases": []}))

    config = load_config(cfg_file)
    report = validate_project(config, tmp_path)

    assert report.passed is True
    assert report.error_count == 0
    assert any(c.name == "Model Identifier" and c.status == "pass" for c in report.checks)
    assert any(c.name == "Dataset Source" and c.status == "pass" for c in report.checks)


def test_validation_engine_missing_resources(tmp_path: Path):
    cfg_data = {
        "project": {"name": "test_proj", "privacy_mode": "local_only"},
        "dataset": {
            "source": "./data/raw/non_existent.jsonl",
            "max_seq_length": 512,
            "validation_ratio": 0.1,
            "eval_ratio": 0.1,
        },
        "model": {"name": "invalid-hf-name", "quantization": "none"},
        "adapter": {"r": 8, "alpha": 16},
        "training": {
            "batch_size": 1,
            "gradient_accumulation_steps": 16,
            "optimizer": "adamw_torch",
            "gradient_checkpointing": True,
            "precision": "fp32",
        },
        "eval": {"suites": [{"path": "./eval/missing.yaml"}]},
        "release": {"require": {"safety_pass": False}},
    }
    cfg_file = tmp_path / "moro.yaml"
    cfg_file.write_text(yaml.safe_dump(cfg_data))

    config = load_config(cfg_file)
    report = validate_project(config, tmp_path)

    assert report.warning_count >= 3
    assert any(c.name == "Dataset Source" and c.status == "warn" for c in report.checks)
    assert any("Eval Suite:" in c.name and c.status == "warn" for c in report.checks)
    assert any(c.name == "Safety Governance" and c.status == "warn" for c in report.checks)

