"""
MoroAI Continuous Learning Flywheel Models.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    """Categorization of feedback signals for preference pairs."""
    EXPLICIT_HUMAN_CORRECTION = "EXPLICIT_HUMAN_CORRECTION"
    IMPLICIT_NEGATIVE_RATING = "IMPLICIT_NEGATIVE_RATING"
    AUTOMATED_RULE_VIOLATION = "AUTOMATED_RULE_VIOLATION"
    POSITIVE_REINFORCEMENT = "POSITIVE_REINFORCEMENT"


class InferenceLogPayload(BaseModel):
    """A single production inference log entry captured from gateways/chat UIs."""
    session_id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    completion: str = Field(..., min_length=1)
    context: str | None = None
    user_rating: float | None = Field(None, ge=-1.0, le=1.0)
    human_correction: str | None = None
    latency_ms: float | None = Field(None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PreferencePair(BaseModel):
    """DPO preference pair (prompt, chosen, rejected) with provenance."""
    pair_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str
    chosen: str
    rejected: str
    feedback_type: FeedbackType
    confidence_delta: float = Field(default=0.5, ge=0.0, le=1.0)
    source_log_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackEntry(BaseModel):
    """File-based production feedback entry (backward-compatible)."""
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_prompt: str
    model_response: str
    human_correction: str | None = None
    implicit_signal: Literal["positive", "negative", "regenerate", "none"] = "none"
    model_version: str | None = None
    tags: list[str] = Field(default_factory=list)


class RefinedTrainingPair(BaseModel):
    """The output of the Flywheel Refiner, ready for data compilation."""
    format: Literal["sft", "dpo"]
    messages: list[dict[str, str]] | None = None
    prompt: str | None = None
    chosen: str | None = None
    rejected: str | None = None
    source_feedback_id: str = ""
    pii_redacted: bool = False
