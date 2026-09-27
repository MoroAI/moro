"""Tests for the Mixing Strategy (Catastrophic Forgetting Guard)."""

import pytest

from moro.recipes.mixing import (
    MixingStrategy,
    calculate_mixing_strategy,
    estimate_jargon_divergence,
)


def test_domain_replay_ratios_sum_to_one():
    """domain_ratio + replay_ratio must always equal 1.0."""
    for model_b in [0.5, 1.0, 1.5, 3.0, 7.0, 8.0]:
        for divergence in [0.0, 0.3, 0.6, 1.0]:
            s = calculate_mixing_strategy(model_b, divergence)
            assert abs(s.domain_ratio + s.replay_ratio - 1.0) < 1e-6, (
                f"Ratios don't sum to 1.0 for {model_b}B, divergence={divergence}: "
                f"{s.domain_ratio} + {s.replay_ratio} = {s.domain_ratio + s.replay_ratio}"
            )


def test_smaller_models_get_more_replay():
    """Smaller models should require more general replay data."""
    small = calculate_mixing_strategy(1.0, jargon_divergence=0.5)
    large = calculate_mixing_strategy(7.0, jargon_divergence=0.5)
    assert small.replay_ratio > large.replay_ratio, (
        f"1B model should need more replay than 7B: {small.replay_ratio} vs {large.replay_ratio}"
    )


def test_higher_divergence_increases_replay():
    """Higher jargon divergence should require more general replay."""
    low = calculate_mixing_strategy(1.5, jargon_divergence=0.0)
    high = calculate_mixing_strategy(1.5, jargon_divergence=1.0)
    assert high.replay_ratio >= low.replay_ratio


def test_replay_ratio_clamped_between_10_and_35_percent():
    """replay_ratio must stay in [0.10, 0.35] regardless of inputs."""
    for model_b in [0.1, 0.5, 1.5, 7.0, 100.0]:
        for divergence in [0.0, 0.5, 1.0]:
            s = calculate_mixing_strategy(model_b, divergence)
            assert 0.10 <= s.replay_ratio <= 0.35, (
                f"replay_ratio={s.replay_ratio} out of [0.10, 0.35] "
                f"for model={model_b}B, divergence={divergence}"
            )


def test_kl_penalty_lambda_range():
    """kl_penalty_lambda must stay in [0.01, 0.15]."""
    for model_b in [0.5, 1.5, 7.0]:
        for divergence in [0.0, 0.5, 1.0]:
            s = calculate_mixing_strategy(model_b, divergence)
            assert 0.01 <= s.kl_penalty_lambda <= 0.15


def test_higher_divergence_increases_kl_penalty():
    """Higher jargon divergence should increase the KL penalty."""
    low = calculate_mixing_strategy(1.5, jargon_divergence=0.0)
    high = calculate_mixing_strategy(1.5, jargon_divergence=1.0)
    assert high.kl_penalty_lambda >= low.kl_penalty_lambda


def test_reasoning_is_non_empty():
    """Every strategy should include a human-readable reasoning string."""
    s = calculate_mixing_strategy(1.5, 0.7)
    assert len(s.reasoning) > 10


def test_effective_batch_split():
    """Batch split should respect the ratios and sum to total_rows."""
    s = calculate_mixing_strategy(1.5, 0.5)
    domain_rows, replay_rows = s.effective_batch_split(1000)
    assert domain_rows + replay_rows == 1000
    assert domain_rows > replay_rows  # domain always dominates


def test_estimate_jargon_divergence():
    """Jargon divergence estimator should return values in [0, 1]."""
    # 0% overlap = fully unique jargon
    d_unique = estimate_jargon_divergence(5000, 0.0)
    assert d_unique == 1.0

    # 100% overlap = all general vocabulary
    d_general = estimate_jargon_divergence(5000, 1.0)
    assert d_general == 0.0

    # 60% overlap = 40% divergence
    d_partial = estimate_jargon_divergence(5000, 0.6)
    assert abs(d_partial - 0.4) < 0.01


def test_divergence_clamped():
    """Divergence should be clamped to [0, 1] even with bad inputs."""
    s_neg = calculate_mixing_strategy(1.5, -0.5)
    s_over = calculate_mixing_strategy(1.5, 2.0)
    
    # Should not raise and should return valid ratios
    assert 0.0 <= s_neg.replay_ratio <= 1.0
    assert 0.0 <= s_over.replay_ratio <= 1.0


def test_known_values_1_5b():
    """Regression test for known values at 1.5B with divergence=0.6."""
    s = calculate_mixing_strategy(1.5, 0.6)
    # 1.5B: s_m = max(0.10, 0.35 - 0.03*1.5) = 0.305
    # beta_raw = 0.305 * (1 + 0.3) = 0.3965 → clamped to 0.35
    # alpha = 0.65
    assert abs(s.replay_ratio - 0.35) < 0.01
    assert abs(s.domain_ratio - 0.65) < 0.01
