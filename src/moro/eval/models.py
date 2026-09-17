from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EvalMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str


class EvalExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contains: list[str] = Field(default_factory=list)
    any_of_contains: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    json_schema: dict[str, Any] | None = None


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    messages: list[EvalMessage]
    expect: EvalExpect | None = None
    tags: list[str] = Field(default_factory=list)


class EvalSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    total_cases: int = Field(ge=1)
    pass_rate: float = Field(ge=0, le=1)
    avg_score: float = Field(ge=0, le=1)
    suite_sha256: str | None = None
    adapter_sha256: str | None = None
    execution_kind: Literal["model", "stub", "legacy"] = "legacy"
    fully_scored: bool = False
    safety_pass: bool | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    cases: list[CaseScore] = Field(default_factory=list)
