from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class HardwareProfile(BaseModel):
    gpu_available: bool
    gpu_vendor: Literal["nvidia", "amd", "apple", "cpu", "unknown"]
    gpu_name: str | None = None
    vram_gb: float | None = None
    cpu_ram_gb: float
    disk_free_gb: float
    python_version: str
    torch_version: str | None = None
    cuda_available: bool = False
    recommended_max_seq_length: int = 1024
    recommended_models: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
