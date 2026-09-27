"""
MoroAI Dataset Models.

Implements the Epistemic Data Schema from the Chief Architect specification.
Every dataset row carries full information-theoretic metadata, enabling
the MI Guard to preserve rare high-value domain examples during cleaning.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ──────────────────────────────────────────────────────────────────────────────
# Epistemic Quality Sub-Models
# ──────────────────────────────────────────────────────────────────────────────

class QualityScoreBreakdown(BaseModel):
    """Weighted quality components (heuristic layer)."""
    completeness: float = Field(default=1.0, ge=0.0, le=1.0)
    length_sanity: float = Field(default=1.0, ge=0.0, le=1.0)
    low_repetition: float = Field(default=1.0, ge=0.0, le=1.0)
    formatting_quality: float = Field(default=1.0, ge=0.0, le=1.0)
    domain_relevance: float = Field(default=1.0, ge=0.0, le=1.0)


class DomainQualityScores(BaseModel):
    """Domain-specific trust dimensions."""
    factual_grounding_score: float = Field(default=1.0, ge=0.0, le=1.0)
    logical_coherence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    instruction_strictness_score: float = Field(default=1.0, ge=0.0, le=1.0)


class InformationTheoreticMetrics(BaseModel):
    """
    CPU-native proxies for Information Theory metrics.

    - zlib_entropy: proxy for Shannon Entropy / Perplexity (via compression ratio).
    - max_ppmi: proxy for Positive Pointwise Mutual Information (glossary intersection density).
    - resnik_ic: proxy for Resnik Information Content (IDF of rarest token).
    - local_vector_density: proxy for neighbourhood isolation (MinHash Jaccard, future).
    """
    zlib_entropy: float = Field(default=0.0, ge=0.0, description="Zlib compression ratio proxy for perplexity")
    max_ppmi: float = Field(default=0.0, ge=0.0, description="Domain glossary intersection density (PPMI proxy)")
    resnik_ic: float = Field(default=0.0, ge=0.0, description="Rarest-token IDF (Resnik IC proxy)")
    local_vector_density: float = Field(default=0.5, ge=0.0, le=1.0, description="MinHash Jaccard density (outlier proxy)")

    @property
    def ppmi_score(self) -> float:
        return self.max_ppmi


# ──────────────────────────────────────────────────────────────────────────────
# Row Classification
# ──────────────────────────────────────────────────────────────────────────────

RowClassification = Literal[
    "HIGH_QUALITY_STANDARD",
    "RARE_HIGH_VALUE_EDGE_CASE",
    "LOW_INFO_BOILERPLATE",
    "NOISY_OUTLIER",
]


class DatasetRowMetadata(BaseModel):
    """
    Full epistemic provenance for a single dataset row.

    This replaces the loose `dict[str, Any]` metadata field with a
    typed schema that enforces information-theoretic consistency.
    """
    domain: Literal["general", "medical", "legal", "financial", "code", "cybersecurity"] = "general"
    language: str = "en"
    token_count: int = Field(default=0, ge=0)

    # Aggregate quality score (0–1)
    quality_score: float = Field(default=1.0, ge=0.0, le=1.0)
    score_breakdown: QualityScoreBreakdown = Field(default_factory=QualityScoreBreakdown)
    domain_scores: DomainQualityScores = Field(default_factory=DomainQualityScores)
    info_metrics: InformationTheoreticMetrics = Field(default_factory=InformationTheoreticMetrics)

    # Epistemic classification
    classification: RowClassification = "HIGH_QUALITY_STANDARD"

    # MI Guard: True when row looks noisy but contains rare, high-value domain facts
    mi_guard_override: bool = Field(
        default=False,
        description="Preserved despite high entropy due to strong domain PPMI / Resnik IC signal.",
    )

    # Privacy & provenance
    pii_detected: bool = False
    privacy_flags: list[str] = Field(default_factory=list)
    duplicate_group: str | None = None
    authority_tier: Literal["official", "draft", "superseded"] | None = "official"
    jurisdiction: str | None = None

    # Raw extra fields for backward compatibility
    extra: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_mi_guard_consistency(self) -> DatasetRowMetadata:
        if self.mi_guard_override and self.classification == "NOISY_OUTLIER":
            raise ValueError(
                "Row cannot be NOISY_OUTLIER when mi_guard_override=True. "
                "The MI Guard promotes noisy-but-valuable rows to RARE_HIGH_VALUE_EDGE_CASE."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
# Core Row Model
# ──────────────────────────────────────────────────────────────────────────────

class DatasetMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class DatasetRow(BaseModel):
    id: str
    source: str
    messages: list[DatasetMessage]

    # Top-level convenience fields (mirrored in metadata for backward compat)
    quality_score: float = 0.0
    token_count: int = 0
    privacy_flags: list[str] = Field(default_factory=list)

    # Full epistemic metadata
    metadata: DatasetRowMetadata = Field(default_factory=DatasetRowMetadata)


class InvalidRow(BaseModel):
    source: str
    line_number: int | None = None
    reason: str
    raw: dict[str, Any] | None = None


# ──────────────────────────────────────────────────────────────────────────────
# Dataset Statistics
# ──────────────────────────────────────────────────────────────────────────────

class DatasetStats(BaseModel):
    rows_total: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    rows_deduplicated: int = 0
    rows_near_duplicate: int = 0
    train_rows: int = 0
    validation_rows: int = 0
    eval_rows: int = 0
    avg_tokens: float = 0.0
    p50_tokens: float = 0.0
    p95_tokens: float = 0.0
    max_tokens: int = 0
    avg_quality_score: float = 0.0
    min_quality_score: float = 0.0
    quality_score_p50: float = 0.0
    privacy_warning_count: int = 0
    warnings: list[str] = Field(default_factory=list)

    # Epistemic classification counts (from Pillar 1)
    classification_counts: dict[str, int] = Field(default_factory=dict)
    mi_guard_count: int = 0
    avg_zlib_entropy: float = 0.0
    avg_ppmi: float = 0.0
    noisy_outlier_count: int = 0
    boilerplate_count: int = 0
    rare_edge_case_count: int = 0
