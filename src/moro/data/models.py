from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class DatasetRow(BaseModel):
    id: str
    source: str
    messages: list[DatasetMessage]
    quality_score: float = 0.0
    token_count: int = 0
    privacy_flags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvalidRow(BaseModel):
    source: str
    line_number: int | None = None
    reason: str
    raw: dict[str, Any] | None = None


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
