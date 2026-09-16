"""
Recipe suggestion engine — wraps presets with hardware + config overrides.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from moro.hardware.profile import HardwareProfile
from moro.recipes.presets import get_preset_for_vram


class RecipeSuggestion(BaseModel):
    model: str
    quantization: Literal["none", "int8", "nf4"]
    adapter_r: int
    adapter_alpha: int
    target_modules: list[str]
    max_seq_length: int
    batch_size: int
    gradient_accumulation_steps: int
    optimizer: Literal["adamw_torch", "adamw_8bit", "paged_adamw_8bit"]
    gradient_checkpointing: bool
    precision: Literal["auto", "bf16", "fp16", "fp32"]
    estimated_vram_gb: float
    confidence: Literal["low", "medium", "high"]
    hardware_tier: str
    warnings: list[str] = Field(default_factory=list)


# Default target modules by model family
_TARGET_MODULES: dict[str, list[str]] = {
    "qwen": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "llama": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "mistral": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "phi": ["q_proj", "k_proj", "v_proj", "dense"],
    "gemma": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "default": ["q_proj", "v_proj"],
}


def _get_target_modules(model_name: str) -> list[str]:
    lower = model_name.lower()
    for family, modules in _TARGET_MODULES.items():
        if family in lower:
            return modules
    return _TARGET_MODULES["default"]


def suggest_recipe(
    hardware: HardwareProfile,
    model_name: str | None = None,
    target_vram: float | None = None,
    max_seq_length: int | None = None,
) -> RecipeSuggestion:
    """
    Suggest a hardware-safe training recipe.

    Args:
        hardware: Detected hardware profile.
        model_name: Override the suggested model.
        target_vram: Override VRAM budget (useful for testing conservative settings).
        max_seq_length: Override maximum sequence length.

    Returns:
        RecipeSuggestion with safe defaults.
    """
    effective_vram = target_vram if target_vram is not None else hardware.vram_gb
    if target_vram is not None and (not math.isfinite(target_vram) or target_vram < 0):
        raise ValueError("VRAM budget must be finite and non-negative.")
    if max_seq_length is not None and not 16 <= max_seq_length <= 32768:
        raise ValueError("Sequence length must be between 16 and 32768.")
    budget_clamped = False
    if hardware.cuda_available and hardware.vram_gb is not None:
        if effective_vram is not None and effective_vram > hardware.vram_gb:
            effective_vram = hardware.vram_gb
            budget_clamped = True
    if not hardware.cuda_available:
        effective_vram = 0
    preset = get_preset_for_vram(effective_vram)

    # Choose model
    if model_name:
        chosen_model = model_name
    elif preset.recommended_models:
        chosen_model = preset.recommended_models[0]
    else:
        chosen_model = "Qwen/Qwen2.5-0.5B-Instruct"

    # Apply seq_length override
    seq_len = max_seq_length if max_seq_length else preset.max_seq_length

    # Respect hardware.recommended_max_seq_length as a hard cap
    seq_len = min(seq_len, hardware.recommended_max_seq_length)

    # Target modules
    target_modules = _get_target_modules(chosen_model)

    # Collect warnings from preset + hardware
    warnings: list[str] = list(preset.notes) + list(hardware.warnings)

    confidence = preset.confidence
    if budget_clamped:
        warnings.append("Requested VRAM budget exceeds detected VRAM; using detected capacity.")
    if effective_vram and preset.estimated_vram_gb > effective_vram:
        confidence = "low"
        warnings.append(
            "Estimated usage exceeds the VRAM budget; this recipe may run out of memory."
        )
    if model_name and model_name != preset.recommended_models[0]:
        confidence = "low"
        warnings.append("Model override: memory estimate applies to the preset model only.")
    if max_seq_length and max_seq_length > preset.max_seq_length:
        confidence = "low"
        warnings.append("Longer sequences may exceed the preset memory estimate.")
    if hardware.gpu_vendor == "apple":
        warnings.append(
            "Apple/MPS training is unverified; using unquantized conservative settings."
        )

    # Non-CUDA warning
    if not hardware.cuda_available and hardware.gpu_vendor not in ("apple",):
        warnings.append(
            "CUDA not available — training will be slow or impossible on this hardware."
        )

    return RecipeSuggestion(
        model=chosen_model,
        quantization=preset.quantization,  # type: ignore[arg-type]
        adapter_r=preset.adapter_r,
        adapter_alpha=preset.adapter_alpha,
        target_modules=target_modules,
        max_seq_length=seq_len,
        batch_size=preset.batch_size,
        gradient_accumulation_steps=preset.gradient_accumulation_steps,
        optimizer=preset.optimizer,  # type: ignore[arg-type]
        gradient_checkpointing=preset.gradient_checkpointing,
        precision=preset.precision,  # type: ignore[arg-type]
        estimated_vram_gb=preset.estimated_vram_gb,
        confidence=confidence,  # type: ignore[arg-type]
        hardware_tier=preset.tier,
        warnings=warnings,
    )
