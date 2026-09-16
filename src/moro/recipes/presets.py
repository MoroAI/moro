"""
Hardware tier presets for recipe suggestion.

Each preset defines safe training defaults for a specific hardware tier.
Tiers are ordered from most constrained (CPU-only) to most capable (24+ GB VRAM).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class RecipePreset:
    tier: str
    vram_min_gb: float
    vram_max_gb: float  # use float('inf') for unlimited
    recommended_models: list[str] = field(default_factory=list)
    quantization: str = "nf4"
    adapter_r: int = 16
    adapter_alpha: int = 32
    max_seq_length: int = 1024
    batch_size: int = 1
    gradient_accumulation_steps: int = 16
    optimizer: str = "paged_adamw_8bit"
    gradient_checkpointing: bool = True
    precision: str = "auto"
    estimated_vram_gb: float = 4.0
    confidence: str = "medium"
    notes: list[str] = field(default_factory=list)


PRESETS: list[RecipePreset] = [
    RecipePreset(
        tier="cpu_only",
        vram_min_gb=0.0,
        vram_max_gb=0.0,
        recommended_models=["Qwen/Qwen2.5-0.5B-Instruct"],
        quantization="none",
        adapter_r=8,
        adapter_alpha=16,
        max_seq_length=512,
        batch_size=1,
        gradient_accumulation_steps=32,
        optimizer="adamw_torch",
        gradient_checkpointing=True,
        precision="fp32",
        estimated_vram_gb=0.0,
        confidence="low",
        notes=[
            "CPU-only training is very slow — use for testing only.",
            "Reduce dataset to < 500 rows for reasonable speed.",
        ],
    ),
    RecipePreset(
        tier="low_vram_4gb",
        vram_min_gb=0.1,
        vram_max_gb=4.9,
        recommended_models=["Qwen/Qwen2.5-0.5B-Instruct"],
        quantization="nf4",
        adapter_r=8,
        adapter_alpha=16,
        max_seq_length=512,
        batch_size=1,
        gradient_accumulation_steps=16,
        optimizer="paged_adamw_8bit",
        gradient_checkpointing=True,
        precision="auto",
        estimated_vram_gb=3.5,
        confidence="medium",
        notes=["Use 0.5B model with NF4 quantization for safe 4 GB VRAM budget."],
    ),
    RecipePreset(
        tier="mid_vram_8gb",
        vram_min_gb=5.0,
        vram_max_gb=9.9,
        recommended_models=[
            "Qwen/Qwen2.5-1.5B-Instruct",
            "Qwen/Qwen2.5-3B-Instruct",
        ],
        quantization="nf4",
        adapter_r=16,
        adapter_alpha=32,
        max_seq_length=1024,
        batch_size=1,
        gradient_accumulation_steps=16,
        optimizer="paged_adamw_8bit",
        gradient_checkpointing=True,
        precision="auto",
        estimated_vram_gb=7.0,
        confidence="high",
        notes=["Good balance for 8 GB GPUs (RTX 3070/4060 class)."],
    ),
    RecipePreset(
        tier="mid_vram_16gb",
        vram_min_gb=10.0,
        vram_max_gb=15.9,
        recommended_models=[
            "Qwen/Qwen2.5-3B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
            "meta-llama/Llama-3.2-3B-Instruct",
        ],
        quantization="nf4",
        adapter_r=16,
        adapter_alpha=32,
        max_seq_length=2048,
        batch_size=2,
        gradient_accumulation_steps=8,
        optimizer="paged_adamw_8bit",
        gradient_checkpointing=True,
        precision="auto",
        estimated_vram_gb=13.0,
        confidence="high",
        notes=["Solid settings for RTX 3080/4070 Ti class GPUs."],
    ),
    RecipePreset(
        tier="high_vram_24gb",
        vram_min_gb=16.0,
        vram_max_gb=float("inf"),
        recommended_models=[
            "Qwen/Qwen2.5-7B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ],
        quantization="nf4",
        adapter_r=32,
        adapter_alpha=64,
        max_seq_length=4096,
        batch_size=4,
        gradient_accumulation_steps=4,
        optimizer="paged_adamw_8bit",
        gradient_checkpointing=False,
        precision="auto",
        estimated_vram_gb=20.0,
        confidence="high",
        notes=["Full 7B/8B class model training. RTX 3090/4090 or better."],
    ),
]


def get_preset_for_vram(vram_gb: float | None) -> RecipePreset:
    """Return the best matching preset for the given VRAM amount."""
    if vram_gb is None:
        return PRESETS[0]
    if not math.isfinite(vram_gb) or vram_gb < 0:
        raise ValueError("VRAM budget must be finite and non-negative.")
    if vram_gb == 0:
        return PRESETS[0]

    # Select by estimated usage, leaving no fractional gaps between tiers.
    for preset in reversed(PRESETS[1:]):
        if preset.estimated_vram_gb <= vram_gb:
            return preset
    return PRESETS[1]
