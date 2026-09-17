"""Tests for recipe engine."""

from moro.hardware.profile import HardwareProfile
from moro.recipes.engine import suggest_recipe


def _make_hardware(vram_gb: float | None, gpu: bool = True) -> HardwareProfile:
    return HardwareProfile(
        gpu_available=gpu and vram_gb is not None and vram_gb > 0,
        gpu_vendor="nvidia" if (gpu and vram_gb) else "cpu",
        gpu_name="Test GPU" if (gpu and vram_gb) else None,
        vram_gb=vram_gb,
        cpu_ram_gb=16.0,
        disk_free_gb=100.0,
        python_version="3.11.0",
        torch_version="2.3.0",
        cuda_available=gpu and bool(vram_gb),
        recommended_max_seq_length=2048 if (vram_gb and vram_gb >= 8) else 1024,
        recommended_models=["Qwen/Qwen2.5-1.5B-Instruct"],
    )


def test_cpu_only_gets_conservative_preset():
    hw = _make_hardware(None, gpu=False)
    recipe = suggest_recipe(hw)
    assert recipe.batch_size == 1
    assert recipe.hardware_tier == "cpu_only"
    assert recipe.confidence == "low"
    assert recipe.max_seq_length <= 512


def test_low_vram_4gb():
    hw = _make_hardware(4.0)
    recipe = suggest_recipe(hw)
    assert recipe.hardware_tier == "low_vram_4gb"
    assert recipe.quantization == "nf4"
    assert recipe.adapter_r <= 16


def test_mid_vram_8gb():
    hw = _make_hardware(8.0)
    recipe = suggest_recipe(hw)
    assert recipe.hardware_tier == "mid_vram_8gb"
    assert recipe.confidence in ("medium", "high")
    assert recipe.max_seq_length >= 1024


def test_high_vram_24gb():
    hw = _make_hardware(24.0)
    recipe = suggest_recipe(hw)
    assert recipe.hardware_tier == "high_vram_24gb"
    assert recipe.confidence != "high"
    assert recipe.adapter_r >= 32


def test_model_override():
    hw = _make_hardware(8.0)
    recipe = suggest_recipe(hw, model_name="mistralai/Mistral-7B-Instruct-v0.3")
    assert recipe.model == "mistralai/Mistral-7B-Instruct-v0.3"
    assert "q_proj" in recipe.target_modules


def test_target_vram_override():
    hw = _make_hardware(24.0)
    # Force conservative recipe by overriding target VRAM
    recipe = suggest_recipe(hw, target_vram=4.0)
    assert recipe.hardware_tier == "low_vram_4gb"


def test_fractional_vram_never_falls_through_to_largest_preset():
    for budget in [0.01, 4.95, 9.95, 15.95, 16.0, 19.99]:
        recipe = suggest_recipe(_make_hardware(budget))
        assert recipe.hardware_tier != "high_vram_24gb"
        if recipe.estimated_vram_gb > budget:
            assert recipe.fit == "over_budget"
            assert recipe.confidence == "low"
            assert any("exceeds" in warning for warning in recipe.warnings)
        else:
            assert recipe.fit == "estimated_fit"


def test_budget_cannot_exceed_detected_capacity():
    recipe = suggest_recipe(_make_hardware(4), target_vram=80)
    assert recipe.hardware_tier == "low_vram_4gb"
    assert any("detected" in warning for warning in recipe.warnings)


def test_non_cuda_does_not_get_bitsandbytes_recipe():
    hardware = _make_hardware(16)
    hardware.cuda_available = False
    hardware.gpu_vendor = "apple"
    recipe = suggest_recipe(hardware)
    assert recipe.quantization == "none"
    assert recipe.optimizer == "adamw_torch"


def test_invalid_budget_rejected():
    import pytest

    for budget in [-1, float("nan"), float("inf")]:
        with pytest.raises(ValueError):
            suggest_recipe(_make_hardware(8), target_vram=budget)


def test_custom_model_estimate_is_not_high_confidence():
    recipe = suggest_recipe(_make_hardware(8), model_name="custom/70B")
    assert recipe.confidence == "low"
    assert any("override" in reason for reason in recipe.reasons)
