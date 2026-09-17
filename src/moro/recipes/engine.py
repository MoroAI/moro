"""
Recipe suggestion engine — wraps presets with hardware + config overrides.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from moro.config.models import MoroConfig
from moro.hardware.profile import HardwareProfile
from moro.recipes.presets import get_preset_for_vram
from moro.recipes.rules import estimate_memory, infer_parameter_billions


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
    estimated_vram_gb: float | None
    estimated_memory_gb: float | None = None
    parameter_billions: float | None = None
    parameter_source: str = "unknown"
    memory_breakdown_gb: dict[str, float] = Field(default_factory=dict)
    target_vram_gb: float | None = None
    fit: Literal["estimated_fit", "over_budget", "unknown"] = "unknown"
    reasons: list[str] = Field(default_factory=list)
    config_patch: dict = Field(default_factory=dict)
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
    config: MoroConfig | None = None,
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

    chosen_model = model_name or (config.model.name if config else preset.recommended_models[0])
    requested_seq = (
        max_seq_length
        if max_seq_length is not None
        else (config.dataset.max_seq_length if config else preset.max_seq_length)
    )
    seq_len = min(requested_seq, hardware.recommended_max_seq_length)
    reasons = ["Preserved the selected model; no model substitution is performed."]
    if seq_len != requested_seq:
        reasons.append(
            f"Sequence length capped from {requested_seq} to {seq_len} by hardware profile."
        )
    quantization = config.model.quantization if config else preset.quantization
    optimizer = config.training.optimizer if config else preset.optimizer
    precision = config.training.precision if config else preset.precision
    if not hardware.cuda_available:
        quantization, optimizer, precision = "none", "adamw_torch", "fp32"
        reasons.append("Non-CUDA settings use unquantized weights, adamw_torch, and fp32.")
    rank = config.adapter.r if config else preset.adapter_r
    alpha = config.adapter.alpha if config else preset.adapter_alpha
    batch = config.training.batch_size if config else preset.batch_size
    accumulation = (
        config.training.gradient_accumulation_steps
        if config
        else preset.gradient_accumulation_steps
    )
    checkpointing = (
        config.training.gradient_checkpointing if config else preset.gradient_checkpointing
    )
    modules = (
        config.adapter.target_modules
        if config and config.adapter.target_modules != "auto"
        else _get_target_modules(chosen_model)
    )
    warnings = list(hardware.warnings)
    warnings.append(
        "Memory estimates are uncalibrated heuristics, not measured hardware validation."
    )
    if budget_clamped:
        warnings.append("Requested VRAM budget exceeds detected VRAM; using detected capacity.")
    billions, source = infer_parameter_billions(chosen_model)
    breakdown = {}
    estimated = None
    fit = "unknown"
    confidence = "low"
    if billions is not None:
        breakdown = estimate_memory(
            billions,
            quantization=quantization,
            precision=precision,
            sequence_length=seq_len,
            batch_size=batch,
            rank=rank,
            module_count=len(modules),
            checkpointing=checkpointing,
            optimizer=optimizer,
        )
        estimated = round(sum(breakdown.values()), 3)
        reasons.append(f"Parameter count from {source}: {billions:g} billion.")
        if hardware.cuda_available and effective_vram is not None:
            fit = "estimated_fit" if estimated <= effective_vram else "over_budget"
            if fit == "estimated_fit":
                confidence = "medium"
            else:
                warnings.append(
                    "Estimated usage exceeds the VRAM budget; "
                    "reduce settings or choose a smaller model."
                )
    else:
        warnings.append("Unknown parameter count: memory usage and fit cannot be estimated.")
    if modules == _TARGET_MODULES["default"] and not (
        config and config.adapter.target_modules != "auto"
    ):
        confidence = "low"
        warnings.append("Unknown model family: verify suggested target modules against the model.")
    if not hardware.cuda_available:
        warnings.append(
            "CPU/MPS memory fit is unverified; the memory estimate is not dedicated VRAM."
        )
    if model_name:
        reasons.append("The --model override takes precedence over the project model.")
    patch = {
        "model": {"name": chosen_model, "quantization": quantization},
        "dataset": {"max_seq_length": seq_len},
        "adapter": {"r": rank, "alpha": alpha, "target_modules": modules},
        "training": {
            "batch_size": batch,
            "gradient_accumulation_steps": accumulation,
            "optimizer": optimizer,
            "gradient_checkpointing": checkpointing,
            "precision": precision,
        },
    }
    return RecipeSuggestion(
        model=chosen_model,
        quantization=quantization,
        adapter_r=rank,
        adapter_alpha=alpha,
        target_modules=modules,
        max_seq_length=seq_len,
        batch_size=batch,
        gradient_accumulation_steps=accumulation,
        optimizer=optimizer,
        gradient_checkpointing=checkpointing,
        precision=precision,
        estimated_vram_gb=estimated if hardware.cuda_available else None,
        estimated_memory_gb=estimated,
        parameter_billions=billions,
        parameter_source=source,
        memory_breakdown_gb=breakdown,
        target_vram_gb=effective_vram if hardware.cuda_available else None,
        fit=fit,
        confidence=confidence,
        hardware_tier=preset.tier,
        warnings=warnings,
        reasons=reasons,
        config_patch=patch,
    )
