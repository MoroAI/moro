from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvalMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class EvalExpect(BaseModel):
    contains: list[str] = Field(default_factory=list)
    any_of_contains: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] | None = None


class EvalCase(BaseModel):
    id: str
    messages: list[EvalMessage]
    expect: EvalExpect | None = None
    tags: list[str] = Field(default_factory=list)


class EvalSuite(BaseModel):
    name: str
    version: str = "1"
    description: str | None = None
    cases: list[EvalCase] = Field(default_factory=list)


class CaseScore(BaseModel):
    case_id: str
    passed: bool
    score: float
    response: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class EvalResult(BaseModel):
    id: str
    suite_name: str
    run_id: str | None = None
    model: str
    created_at: datetime
    total_cases: int
    pass_rate: float
    avg_score: float
    metrics: dict[str, float] = Field(default_factory=dict)
    cases: list[CaseScore] = Field(default_factory=list)
