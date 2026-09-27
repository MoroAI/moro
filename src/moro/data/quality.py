"""
MoroAI Information-Theoretic Quality Engine.

Implements CPU-native proxies for 4 key IT metrics:

1. Zlib Entropy (perplexity proxy via compression ratio)
   - High ratio → noisy/gibberish (high entropy)
   - Low ratio → repetitive boilerplate (low entropy)
   - Optimal band → rich, structured domain text

2. PPMI Proxy (domain relevance via glossary intersection density)

3. Resnik IC Proxy (concept rarity via IDF of rarest token)

4. Classification & MI Guard
   - RARE_HIGH_VALUE_EDGE_CASE: high entropy but strong domain signal → SAVE IT
   - NOISY_OUTLIER: high entropy, no domain signal → filter
   - LOW_INFO_BOILERPLATE: very low entropy → filter
   - HIGH_QUALITY_STANDARD: default

No external LLM calls required. Runs on CPU in milliseconds per row.
"""

from __future__ import annotations

import math
import re
import zlib
from collections import Counter
from typing import Optional

from moro.data.models import (
    DatasetMessage,
    DatasetRow,
    DatasetRowMetadata,
    DomainQualityScores,
    InformationTheoreticMetrics,
    QualityScoreBreakdown,
    RowClassification,
)


# ──────────────────────────────────────────────────────────────────────────────
# Information-Theoretic Metric Proxies
# ──────────────────────────────────────────────────────────────────────────────

def calculate_zlib_entropy(text: str) -> float:
    """
    Proxy for Perplexity / Information Density via zlib compression ratio.

    compression_ratio = compressed_size / original_size

    - ratio < 0.15: repetitive boilerplate (very low entropy)
    - ratio 0.15–0.45: optimal domain text (Goldilocks band)
    - ratio > 0.45: noisy/gibberish or highly random text

    Returns compression ratio in [0, 1].
    """
    if not text:
        return 0.0
    text_bytes = text.encode("utf-8")
    if len(text_bytes) < 10:
        return 1.0  # Too short to compress meaningfully
    compressed = zlib.compress(text_bytes, level=6)
    return len(compressed) / len(text_bytes)


def calculate_domain_ppmi(text: str, domain_glossary: set[str]) -> float:
    """
    Proxy for Positive Pointwise Mutual Information (domain relevance).

    Measures density of domain-specific terminology using glossary intersection.
    Returns a scaled score in [0, ∞) — typically 0–10.

    score = (|text_words ∩ glossary| / |text_words|) * 10
    """
    if not domain_glossary:
        return 0.0

    words = set(re.findall(r"\b\w+\b", text.lower()))
    if not words:
        return 0.0

    matches = words.intersection(domain_glossary)
    return (len(matches) / len(words)) * 10.0


def calculate_resnik_ic(
    text: str,
    global_token_counts: Counter,
    total_docs: int,
) -> float:
    """
    Proxy for Resnik Information Content: IC(c) = -log(P(c)).

    We use the IDF of the rarest token in the row. A row containing very
    rare, domain-specific terms will have a high Resnik IC score — these
    are high-value examples that must not be discarded.

    Returns IC score ≥ 0 (higher = rarer = more valuable).
    """
    words = re.findall(r"\b\w+\b", text.lower())
    if not words or total_docs == 0:
        return 0.0

    min_prob = 1.0
    for w in words:
        count = global_token_counts.get(w, 1)
        prob = count / total_docs
        if prob < min_prob:
            min_prob = prob

    return -math.log(min_prob + 1e-9)


# ──────────────────────────────────────────────────────────────────────────────
# Basic Quality Breakdown (heuristic layer)
# ──────────────────────────────────────────────────────────────────────────────

def compute_basic_quality_breakdown(row: DatasetRow) -> QualityScoreBreakdown:
    """Compute foundational heuristic quality scores."""
    roles = {msg.role for msg in row.messages}
    completeness = 1.0 if {"user", "assistant"}.issubset(roles) else 0.0

    all_text = " ".join(msg.content for msg in row.messages)
    tokens = all_text.split()
    token_count = len(tokens)

    # Length sanity
    if token_count <= 0:
        length_sanity = 0.0
    elif token_count < 8:
        length_sanity = token_count / 8.0
    elif token_count <= 4096:
        length_sanity = 1.0
    else:
        length_sanity = max(0.0, 1.0 - ((token_count - 4096) / 4096))

    # Vocabulary diversity (repetition proxy)
    unique_ratio = len(set(tokens)) / max(1, token_count)
    low_repetition = max(0.0, min(1.0, unique_ratio))

    # Formatting
    formatting = 1.0 if all(msg.content.strip() for msg in row.messages) else 0.0

    return QualityScoreBreakdown(
        completeness=completeness,
        length_sanity=length_sanity,
        low_repetition=low_repetition,
        formatting_quality=formatting,
        domain_relevance=1.0,  # Updated later by PPMI calculation
    )


# ──────────────────────────────────────────────────────────────────────────────
# MI Guard Classification
# ──────────────────────────────────────────────────────────────────────────────

# Tunable thresholds (can later be exposed in moro.yaml)
_HIGH_ENTROPY_THRESHOLD = 0.45   # Above this → likely gibberish/HTML
_LOW_ENTROPY_THRESHOLD = 0.15    # Below this → repetitive boilerplate
_HIGH_PPMI_THRESHOLD = 0.5       # Strong domain signal (PPMI > 0.5 after normalization)
_HIGH_IC_THRESHOLD = 8.0         # Very rare concept (Resnik IC > 8.0)


def classify_row(
    entropy: float,
    ppmi: float,
    resnik_ic: float,
    is_duplicate: bool,
) -> tuple[RowClassification, bool]:
    """
    The Density-Aware Latent Filter (MI Guard).

    Returns (classification, mi_guard_override).

    The MI Guard: if a row looks noisy (high entropy) BUT contains strong
    domain signal (high PPMI or very rare concept via Resnik IC), we SAVE
    it by classifying it as RARE_HIGH_VALUE_EDGE_CASE with mi_guard_override=True.

    Without the MI Guard: domain experts' carefully crafted responses would
    be silently discarded because they use rare, specific terminology that
    raises the entropy proxy.
    """
    if is_duplicate:
        return "LOW_INFO_BOILERPLATE", False

    is_noisy = entropy > _HIGH_ENTROPY_THRESHOLD
    is_boilerplate = entropy < _LOW_ENTROPY_THRESHOLD

    # Normalize PPMI to 0–1 for thresholding
    normalized_ppmi = ppmi / 10.0
    has_domain_signal = normalized_ppmi >= _HIGH_PPMI_THRESHOLD or resnik_ic >= _HIGH_IC_THRESHOLD

    # ── THE MI GUARD ───────────────────────────────────────────────────────
    # If it looks noisy but contains rare domain facts → PRESERVE IT
    if is_noisy and has_domain_signal:
        return "RARE_HIGH_VALUE_EDGE_CASE", True  # mi_guard_override=True

    # Standard classifications
    if is_noisy:
        return "NOISY_OUTLIER", False

    if is_boilerplate and not has_domain_signal:
        return "LOW_INFO_BOILERPLATE", False

    if has_domain_signal:
        return "RARE_HIGH_VALUE_EDGE_CASE", False

    return "HIGH_QUALITY_STANDARD", False


# ──────────────────────────────────────────────────────────────────────────────
# Composite Scoring (backward-compatible entry point)
# ──────────────────────────────────────────────────────────────────────────────

def approximate_token_count(messages: list[DatasetMessage]) -> int:
    """
    Fast token approximation using word splitting.
    Heuristic: ~0.75 words per token on average for English text.
    """
    total_words = sum(len(m.content.split()) for m in messages)
    return max(1, int(total_words / 0.75))


def score_row(row: DatasetRow, token_count: int | None = None) -> float:
    """
    Compute a 0.0–1.0 quality score for a dataset row.

    This is the fast path used when global stats aren't available.
    For full epistemic scoring, use `score_row_epistemic()`.

    Components (weighted):
    - Completeness (30%)  — has both user and assistant turns
    - Length sanity (25%) — token count in useful range
    - Repetition (25%)    — vocabulary diversity
    - Formatting (20%)    — no empty message content
    """
    if token_count is None:
        token_count = approximate_token_count(row.messages)

    roles = {m.role for m in row.messages}
    if not {"user", "assistant"}.issubset(roles):
        return 0.0

    completeness = 1.0

    if token_count <= 0:
        length_sanity = 0.0
    elif token_count < 8:
        length_sanity = token_count / 8.0
    elif token_count <= 4096:
        length_sanity = 1.0
    else:
        length_sanity = max(0.0, 1.0 - ((token_count - 4096) / 4096))

    all_text = " ".join(m.content for m in row.messages).lower()
    tokens = all_text.split()
    unique_ratio = len(set(tokens)) / len(tokens) if tokens else 0.0
    repetition_score = max(0.0, min(1.0, unique_ratio))

    formatting = 1.0 if all(m.content.strip() for m in row.messages) else 0.0

    score = (
        0.30 * completeness
        + 0.25 * length_sanity
        + 0.25 * repetition_score
        + 0.20 * formatting
    )
    return round(max(0.0, min(1.0, score)), 4)


def score_row_epistemic(
    row: DatasetRow,
    domain_glossary: set[str],
    global_token_counts: Counter,
    total_docs: int,
    is_duplicate: bool = False,
) -> DatasetRowMetadata:
    """
    Full epistemic scoring: returns a complete DatasetRowMetadata.

    This is the premium path used by `moro data build`. It computes:
    - Basic quality breakdown (heuristics)
    - Information-theoretic metrics (zlib entropy, PPMI, Resnik IC)
    - MI Guard classification
    - Aggregate quality score
    """
    all_text = " ".join(msg.content for msg in row.messages)
    token_count = approximate_token_count(row.messages)

    # 1. Basic quality breakdown
    breakdown = compute_basic_quality_breakdown(row)

    # 2. Information-theoretic metrics
    entropy = calculate_zlib_entropy(all_text)
    ppmi = calculate_domain_ppmi(all_text, domain_glossary)
    resnik_ic = calculate_resnik_ic(all_text, global_token_counts, total_docs)

    # Update domain_relevance in breakdown with normalized PPMI
    breakdown = QualityScoreBreakdown(
        completeness=breakdown.completeness,
        length_sanity=breakdown.length_sanity,
        low_repetition=breakdown.low_repetition,
        formatting_quality=breakdown.formatting_quality,
        domain_relevance=min(1.0, ppmi / 2.0),  # normalize PPMI 0-5 → 0-1 range
    )

    info_metrics = InformationTheoreticMetrics(
        zlib_entropy=round(entropy, 4),
        max_ppmi=round(ppmi, 4),
        resnik_ic=round(resnik_ic, 4),
        local_vector_density=0.5,  # MinHash placeholder — future enhancement
    )

    # 3. Aggregate quality score (5 components)
    quality_score = round(
        0.30 * breakdown.completeness
        + 0.20 * breakdown.length_sanity
        + 0.20 * breakdown.low_repetition
        + 0.10 * breakdown.formatting_quality
        + 0.20 * breakdown.domain_relevance,
        4,
    )

    # 4. MI Guard classification
    classification, mi_guard = classify_row(entropy, ppmi, resnik_ic, is_duplicate)

    return DatasetRowMetadata(
        token_count=token_count,
        quality_score=quality_score,
        score_breakdown=breakdown,
        info_metrics=info_metrics,
        classification=classification,
        mi_guard_override=mi_guard,
        pii_detected=len(row.privacy_flags) > 0,
        privacy_flags=list(row.privacy_flags),
    )
