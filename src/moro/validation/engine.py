"""
MoroAI Pre-Flight Validation Engine.

Performs static and dynamic pre-flight verification before training or deployment:
- Model identifier syntax and HF convention
- Memory and VRAM fit for model + max_seq_length
- Dataset path and split ratio viability
- Eval suite configuration and schema validity
- Release gates threshold feasibility
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from moro.config.models import MoroConfig
from moro.hardware.detector import detect_hardware
from moro.hardware.profile import HardwareProfile
from moro.recipes.rules import estimate_memory, infer_parameter_billions


class ValidationCheck(BaseModel):
    name: str
    status: str  # "pass", "warn", "fail"
    message: str


class ValidationReport(BaseModel):
    passed: bool
    checks: list[ValidationCheck]
    error_count: int
    warning_count: int

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def validate_project(config: MoroConfig, root: Path) -> ValidationReport:
    """Run comprehensive pre-flight verification on a MoroAI project."""
    checks: list[ValidationCheck] = []
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Model Identifier Check
    model_name = config.model.name
    hf_pattern = r"^[a-zA-Z0-9_\-\.]+\/[a-zA-Z0-9_\-\.]+$"
    if "/" in model_name:
        if re.match(hf_pattern, model_name):
            checks.append(ValidationCheck(name="Model Identifier", status="pass", message=f"Valid HuggingFace repository: {model_name}"))
        else:
            checks.append(ValidationCheck(name="Model Identifier", status="warn", message=f"Non-standard HF repository format: {model_name}"))
            warnings.append(f"Model name '{model_name}' has non-standard characters.")
    else:
        checks.append(ValidationCheck(name="Model Identifier", status="warn", message=f"Standalone model identifier: {model_name}"))

    # 2. Hardware & Memory Pre-Flight Check
    raw_hw = detect_hardware()
    hw = HardwareProfile.model_validate(raw_hw)
    param_b, _ = infer_parameter_billions(model_name)
    param_billions = param_b if param_b is not None else 1.5

    quant = config.model.quantization if config.model.quantization in ("nf4", "int8", "none") else "nf4"
    module_count = len(config.adapter.target_modules) if isinstance(config.adapter.target_modules, list) else 7

    mem_dict = estimate_memory(
        param_billions,
        quantization=quant,
        precision=config.training.precision,
        sequence_length=config.dataset.max_seq_length,
        batch_size=config.training.batch_size,
        rank=config.adapter.r,
        module_count=module_count,
        checkpointing=config.training.gradient_checkpointing,
        optimizer=config.training.optimizer,
    )
    est_mem = sum(mem_dict.values())

    if hw.cuda_available and hw.vram_gb is not None:
        if est_mem and est_mem > hw.vram_gb:
            checks.append(ValidationCheck(
                name="Hardware VRAM Fit",
                status="fail",
                message=f"Estimated memory ({est_mem:.1f} GB) exceeds available VRAM ({hw.vram_gb:.1f} GB).",
            ))
            errors.append(f"Insufficient VRAM: estimated {est_mem:.1f} GB > {hw.vram_gb:.1f} GB.")
        else:
            checks.append(ValidationCheck(
                name="Hardware VRAM Fit",
                status="pass",
                message=f"Estimated memory ({est_mem:.1f} GB) fits in {hw.vram_gb:.1f} GB VRAM.",
            ))
    else:
        checks.append(ValidationCheck(
            name="Hardware Compatibility",
            status="pass",
            message=f"CPU/MPS mode with {hw.cpu_ram_gb:.1f} GB host RAM (Estimated: {est_mem:.1f} GB).",
        ))

    # 3. Dataset Configuration Check
    source_path = root / config.dataset.source
    if not source_path.exists():
        checks.append(ValidationCheck(
            name="Dataset Source",
            status="warn",
            message=f"Source dataset not found at: {source_path}. Run moro import.",
        ))
        warnings.append(f"Dataset source file missing: {source_path}")
    else:
        checks.append(ValidationCheck(
            name="Dataset Source",
            status="pass",
            message=f"Dataset source file exists: {source_path.name}",
        ))

    split_sum = config.dataset.validation_ratio + config.dataset.eval_ratio
    if split_sum >= 0.8:
        checks.append(ValidationCheck(
            name="Dataset Split Ratios",
            status="fail",
            message=f"Validation + Eval ratios ({split_sum:.1%}) leave less than 20% for training.",
        ))
        errors.append(f"Split ratio sum {split_sum:.1%} is excessive.")
    else:
        checks.append(ValidationCheck(
            name="Dataset Split Ratios",
            status="pass",
            message=f"Split allocation: Train={1.0 - split_sum:.1%}, Val={config.dataset.validation_ratio:.1%}, Eval={config.dataset.eval_ratio:.1%}",
        ))

    # 4. Eval Suite Existence Check
    for suite_ref in config.eval.suites:
        suite_path = root / suite_ref.path
        if not suite_path.exists():
            checks.append(ValidationCheck(
                name=f"Eval Suite: {suite_ref.path}",
                status="warn",
                message=f"Eval suite file not found at {suite_path}",
            ))
            warnings.append(f"Eval suite missing: {suite_ref.path}")
        else:
            try:
                content = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
                if "cases" in content or "name" in content:
                    checks.append(ValidationCheck(
                        name=f"Eval Suite: {suite_path.name}",
                        status="pass",
                        message=f"Valid evaluation suite schema ({len(content.get('cases', []))} cases).",
                    ))
                else:
                    checks.append(ValidationCheck(
                        name=f"Eval Suite: {suite_path.name}",
                        status="warn",
                        message="Missing 'cases' or 'name' in suite YAML.",
                    ))
            except Exception as e:
                checks.append(ValidationCheck(
                    name=f"Eval Suite: {suite_path.name}",
                    status="fail",
                    message=f"YAML parsing error: {e}",
                ))
                errors.append(f"Eval suite '{suite_path.name}' corrupt: {e}")

    # 5. Release Governance Check
    if config.release.require.safety_pass:
        checks.append(ValidationCheck(
            name="Safety Governance",
            status="pass",
            message="Release safety gate enabled (requires PII clean & eval pass).",
        ))
    else:
        checks.append(ValidationCheck(
            name="Safety Governance",
            status="warn",
            message="Release safety gate is disabled in moro.yaml.",
        ))
        warnings.append("release.require.safety_pass is set to false.")

    passed = len(errors) == 0
    return ValidationReport(
        passed=passed,
        checks=checks,
        error_count=len(errors),
        warning_count=len(warnings),
    )
