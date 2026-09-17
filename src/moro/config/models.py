from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectConfig(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    privacy_mode: Literal["local_only", "allow_external"] = "local_only"
    seed: int = Field(default=42, ge=0)


class DatasetConfig(BaseModel):
    source: Path
    format: Literal["auto", "jsonl", "csv", "txt", "markdown"] = "auto"
    deduplicate: bool = True
    pii_scan: bool = False
    max_seq_length: int = Field(default=1024, ge=16, le=32768)
    min_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    validation_ratio: float = Field(default=0.1, ge=0.0, le=0.5)
    eval_ratio: float = Field(default=0.1, ge=0.0, le=0.5)

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: Path) -> Path:
        if not v:
            raise ValueError("dataset.source is required")
        return Path(v)


class ModelConfig(BaseModel):
    name: str
    revision: str | None = None
    quantization: Literal["none", "int8", "nf4"] = "nf4"
    trust_remote_code: bool = False


class AdapterConfig(BaseModel):
    type: Literal["lora"] = "lora"
    r: int = Field(default=16, ge=1, le=256)
    alpha: int = Field(default=32, ge=1, le=512)
    dropout: float = Field(default=0.05, ge=0.0, le=1.0)
    target_modules: Literal["auto"] | list[str] = "auto"
    bias: Literal["none", "all", "lora_only"] = "none"


class TrainingConfig(BaseModel):
    output_dir: Path = Path("runs")
    batch_size: int = Field(default=1, ge=1)
    gradient_accumulation_steps: int = Field(default=16, ge=1)
    learning_rate: float = Field(default=2e-4, gt=0)
    optimizer: Literal[
        "adamw_torch",
        "adamw_8bit",
        "paged_adamw_8bit",
    ] = "paged_adamw_8bit"
    gradient_checkpointing: bool = True
    precision: Literal["auto", "bf16", "fp16", "fp32"] = "auto"
    epochs: float = Field(default=1.0, gt=0)
    max_steps: int | None = Field(default=None, ge=1)
    warmup_ratio: float = Field(default=0.03, ge=0.0, le=1.0)
    logging_steps: int = Field(default=10, ge=1)
    save_steps: int = Field(default=100, ge=1)

    @field_validator("output_dir")
    @classmethod
    def coerce_output_dir(cls, v: Path) -> Path:
        return Path(v)


class EvalSuiteRef(BaseModel):
    path: Path
    name: str | None = None


class EvalConfig(BaseModel):
    suites: list[EvalSuiteRef] = Field(default_factory=list)
    base_model: str | None = None
    max_samples: int | None = Field(default=None, ge=1)


class ReleaseRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_pass_rate: float | None = Field(default=None, ge=0, le=1)
    eval_suite: str | None = None
    min_improvement: float | None = None
    max_regression: float | None = None
    safety_pass: bool = True


class ReleaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export: list[Literal["adapter", "merged", "gguf", "ollama"]] = Field(
        default_factory=lambda: ["adapter", "ollama"]
    )
    require: ReleaseRequirements | None = None


class MoroConfig(BaseModel):
    project: ProjectConfig
    dataset: DatasetConfig
    model: ModelConfig
    adapter: AdapterConfig = Field(default_factory=AdapterConfig)
    training: TrainingConfig = Field(default_factory=TrainingConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    release: ReleaseConfig = Field(default_factory=ReleaseConfig)

    @field_validator("project", "dataset", "model")
    @classmethod
    def required_sections(cls, v: Any) -> Any:
        if v is None:
            raise ValueError("required config section is missing")
        return v
