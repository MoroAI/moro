"""Tests for export merge and GGUF modules — no real model loading."""

import json
from pathlib import Path

import pytest

from moro.core.errors import ExportError


def _make_fake_adapter(path: Path, base_model: str = "owner/TestModel") -> Path:
    """Create a minimal fake PEFT adapter directory."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "adapter_config.json").write_text(
        json.dumps(
            {
                "peft_type": "LORA",
                "r": 16,
                "lora_alpha": 32,
                "base_model_name_or_path": base_model,
                "revision": None,
            }
        ),
        encoding="utf-8",
    )
    # Fake weights file
    (path / "adapter_model.safetensors").write_bytes(b"\x00" * 64)
    return path


def test_write_gguf_script_creates_file(tmp_path: Path):
    from moro.export.gguf import write_gguf_script

    merged_dir = tmp_path / "merged"
    merged_dir.mkdir()
    out_dir = tmp_path / "gguf"

    script = write_gguf_script(
        merged_model_dir=merged_dir,
        out_dir=out_dir,
        quantization="q4_k_m",
        project_name="my-project",
    )
    assert script.exists()
    assert script.suffix == ".sh"
    content = script.read_text()
    assert "llama.cpp" in content
    assert "q4_k_m" in content
    assert "my-project" in content
    assert str(merged_dir.resolve()) in content


def test_write_gguf_script_is_executable(tmp_path: Path):
    from moro.export.gguf import write_gguf_script

    merged_dir = tmp_path / "merged"
    merged_dir.mkdir()
    script = write_gguf_script(
        merged_model_dir=merged_dir,
        out_dir=tmp_path / "gguf",
        quantization="q5_k_m",
        project_name="test",
    )
    import stat

    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR  # owner execute bit set


def test_convert_to_gguf_direct_rejects_missing_llama_cpp(tmp_path: Path):
    from moro.export.gguf import convert_to_gguf_direct

    merged_dir = tmp_path / "merged"
    merged_dir.mkdir()

    with pytest.raises(ExportError, match="convert_hf_to_gguf"):
        convert_to_gguf_direct(
            merged_model_dir=merged_dir,
            out_dir=tmp_path / "out",
            llama_cpp_path=tmp_path / "nonexistent_llama_cpp",
            quantization="q4_k_m",
        )


def test_merge_adapter_rejects_missing_directory(tmp_path: Path):
    from moro.export.merge import merge_adapter_into_base

    with pytest.raises(Exception):  # DependencyError (no torch) or ExportError
        merge_adapter_into_base(
            adapter_path=tmp_path / "nonexistent_adapter",
            output_dir=tmp_path / "out",
            local_only=True,
        )


def test_merge_adapter_rejects_non_adapter_dir(tmp_path: Path):
    from moro.export.merge import merge_adapter_into_base

    # Directory exists but no adapter_config.json
    bad_dir = tmp_path / "bad_adapter"
    bad_dir.mkdir()

    with pytest.raises(Exception):  # DependencyError or ExportError
        merge_adapter_into_base(
            adapter_path=bad_dir,
            output_dir=tmp_path / "out",
            local_only=True,
        )
