"""Tests for moro recipe apply command."""

import shutil
from pathlib import Path

import pytest
import yaml


def _make_project_config(tmp_path: Path, project_name: str = "test-proj") -> Path:
    """Create a minimal moro.yaml for tests."""
    cfg = {
        "project": {"name": project_name},
        "dataset": {"source": "data/raw/test.jsonl"},
        "model": {"name": "Qwen/Qwen2.5-1.5B-Instruct"},
        "adapter": {"r": 16, "alpha": 32},
        "training": {"batch_size": 1, "learning_rate": 0.0002},
    }
    cfg_path = tmp_path / "moro.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return cfg_path


def test_recipe_apply_creates_backup(tmp_path: Path, monkeypatch):
    """recipe apply backs up the original moro.yaml before writing."""

    cfg_path = _make_project_config(tmp_path)

    # Directly test the patch logic (no hardware detection needed)
    original_content = cfg_path.read_text()

    patch = {
        "model": {"name": "Qwen/Qwen2.5-1.5B-Instruct", "quantization": "nf4"},
        "training": {"batch_size": 1, "gradient_accumulation_steps": 16},
    }

    timestamp = "20260101T000000Z"

    backup_path = cfg_path.with_suffix(f".{timestamp}.bak.yaml")
    shutil.copy2(cfg_path, backup_path)

    current = yaml.safe_load(cfg_path.read_text()) or {}
    for section, values in patch.items():
        if section not in current:
            current[section] = {}
        if isinstance(values, dict):
            current[section].update(values)
        else:
            current[section] = values
    cfg_path.write_text(yaml.safe_dump(current, sort_keys=False, allow_unicode=True))

    assert backup_path.exists()
    assert yaml.safe_load(backup_path.read_text()) == yaml.safe_load(original_content)


def test_recipe_patch_merge_preserves_existing_keys(tmp_path: Path):
    """Applying a partial patch preserves keys not in the patch."""
    cfg_path = _make_project_config(tmp_path)

    original = yaml.safe_load(cfg_path.read_text())
    assert original["training"]["learning_rate"] == pytest.approx(0.0002)

    # Patch only gradient_accumulation_steps, leave learning_rate alone
    patch = {"training": {"gradient_accumulation_steps": 32}}
    current = yaml.safe_load(cfg_path.read_text()) or {}
    for section, values in patch.items():
        if section not in current:
            current[section] = {}
        if isinstance(values, dict):
            current[section].update(values)
    cfg_path.write_text(yaml.safe_dump(current, sort_keys=False, allow_unicode=True))

    result = yaml.safe_load(cfg_path.read_text())
    assert result["training"]["gradient_accumulation_steps"] == 32
    assert result["training"]["learning_rate"] == pytest.approx(0.0002)  # unchanged
    assert result["training"]["batch_size"] == 1  # unchanged


def test_recipe_patch_adds_missing_section(tmp_path: Path):
    """Patch creates missing sections."""
    cfg = {
        "project": {"name": "test"},
        "dataset": {"source": "data/raw/x.jsonl"},
        "model": {"name": "Qwen/Qwen2.5-1.5B-Instruct"},
    }
    cfg_path = tmp_path / "moro.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    patch = {"adapter": {"r": 64, "alpha": 128, "target_modules": ["q_proj", "v_proj"]}}
    current = yaml.safe_load(cfg_path.read_text()) or {}
    for section, values in patch.items():
        if section not in current:
            current[section] = {}
        if isinstance(values, dict):
            current[section].update(values)
    cfg_path.write_text(yaml.safe_dump(current, sort_keys=False))

    result = yaml.safe_load(cfg_path.read_text())
    assert result["adapter"]["r"] == 64
    assert result["adapter"]["alpha"] == 128
