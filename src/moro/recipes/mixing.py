"""
MoroAI Auto-Ratio Formula for Data Mixing.

Prevents catastrophic forgetting in small LLMs (1B–8B) when fine-tuning
on narrow domain data. Without general replay data, models rapidly forget
how to follow instructions — they gain domain knowledge but lose conversational
ability.

The Auto-Ratio Formula calculates:
  - domain_ratio (α): fraction of training data that should be domain-specific
  - replay_ratio (β): fraction that should be general instruction-following replay
  - kl_penalty_lambda: regularization strength to anchor to the base distribution

Based on:
  - Model Parameter Scale Factor (S_M): smaller models need more replay
  - Jargon Divergence Score: higher divergence → more replay to prevent forgetting

Usage:
    from moro.recipes.mixing import calculate_mixing_strategy
    strategy = calculate_mixing_strategy(model_size_billions=1.5, jargon_divergence=0.7)
    # → MixingStrategy(domain_ratio=0.72, replay_ratio=0.28, kl_penalty_lambda=0.064)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MixingStrategy(BaseModel):
    """
    Data mixing strategy for preventing catastrophic forgetting.

    domain_ratio + replay_ratio = 1.0 (always)
    """
    domain_ratio: float = Field(..., ge=0.0, le=1.0, description="Fraction of domain-specific training data")
    replay_ratio: float = Field(..., ge=0.0, le=1.0, description="Fraction of general replay data")
    kl_penalty_lambda: float = Field(..., ge=0.0, description="KL divergence regularization strength")
    reasoning: str = Field(default="", description="Human-readable explanation of the calculation")

    model_config = {"frozen": False}  # allow computed fields during validation

    def effective_batch_split(self, total_rows: int) -> tuple[int, int]:
        """Given a total row count, return (domain_rows, replay_rows)."""
        domain_rows = round(total_rows * self.domain_ratio)
        replay_rows = total_rows - domain_rows
        return domain_rows, replay_rows


def calculate_mixing_strategy(
    model_size_billions: float,
    jargon_divergence: float,
) -> MixingStrategy:
    """
    Calculate the optimal data mixing strategy using the MoroAI Auto-Ratio Formula.

    Args:
        model_size_billions: Model parameter count in billions (e.g., 1.5 for Qwen2.5-1.5B).
        jargon_divergence: Domain vocabulary divergence score [0.0, 1.0].
            0.0 = general language (low catastrophic forgetting risk)
            1.0 = highly specialized jargon (high catastrophic forgetting risk)
            Estimated from dataset report's vocabulary diversity score.

    Returns:
        MixingStrategy with domain_ratio, replay_ratio, and kl_penalty_lambda.

    Formula derivation:
        1. S_M = max(0.10, 0.35 - 0.03 * model_size_billions)
           → Smaller models (1B) have S_M ≈ 0.32 (need more replay)
           → Larger models (7B) have S_M ≈ 0.14 (retain more capacity)

        2. β_raw = S_M × (1 + jargon_divergence / 2)
           → High jargon divergence pushes more replay requirement

        3. β (replay_ratio) = clamp(β_raw, 0.10, 0.35)
           → Never below 10% replay (minimum anchor)
           → Never above 35% replay (domain data must dominate)

        4. α (domain_ratio) = 1.0 - β

        5. λ (kl_lambda) = clamp(0.05 + jargon_divergence × 0.02, 0.01, 0.15)
           → Stronger anchor to base distribution when jargon is very different
    """
    b = float(model_size_billions)
    d = max(0.0, min(1.0, float(jargon_divergence)))

    # 1. Model Parameter Scale Factor
    s_m = max(0.10, 0.35 - (0.03 * b))

    # 2. Raw replay ratio
    beta_raw = s_m * (1.0 + (d / 2.0))

    # 3. Clamped replay ratio
    beta_general = max(0.10, min(0.35, beta_raw))

    # 4. Domain ratio
    alpha_domain = 1.0 - beta_general

    # 5. KL penalty
    kl_lambda = max(0.01, min(0.15, 0.05 + (d * 0.02)))

    reasoning = (
        f"Model {b:.1f}B → scale_factor={s_m:.2f}. "
        f"Jargon divergence={d:.2f} → β_raw={beta_raw:.2f}, "
        f"β_clamped={beta_general:.2f}. "
        f"domain_ratio={alpha_domain:.2f}, replay_ratio={beta_general:.2f}, "
        f"kl_lambda={kl_lambda:.4f}."
    )

    return MixingStrategy(
        domain_ratio=round(alpha_domain, 3),
        replay_ratio=round(beta_general, 3),
        kl_penalty_lambda=round(kl_lambda, 4),
        reasoning=reasoning,
    )


def estimate_jargon_divergence(
    domain_vocab_size: int,
    general_vocab_overlap_ratio: float,
) -> float:
    """
    Estimate jargon divergence from dataset vocabulary statistics.

    Args:
        domain_vocab_size: Number of unique tokens in the domain dataset.
        general_vocab_overlap_ratio: Fraction of domain tokens that also
            appear in a general corpus. 0 = entirely unique, 1 = all general.

    Returns:
        Divergence score in [0.0, 1.0]. Higher = more specialized.
    """
    # Fraction of tokens NOT in the general corpus = divergence
    divergence = 1.0 - general_vocab_overlap_ratio
    return round(max(0.0, min(1.0, divergence)), 4)
