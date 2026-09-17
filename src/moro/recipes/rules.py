"""Offline model-size hints and deliberately uncalibrated memory heuristics."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path


def infer_parameter_billions(model: str) -> tuple[float | None, str]:
    """Prefer an explicit local parameter count; never guess an unknown model is small."""
    path = Path(model).expanduser()
    if path.is_dir():
        try:
            metadata = json.loads((path / "config.json").read_text(encoding="utf-8"))
            count = metadata.get("num_parameters")
            if (
                isinstance(count, (int, float))
                and not isinstance(count, bool)
                and math.isfinite(count)
                and count > 0
            ):
                return count / 1e9, "local_config"
        except (OSError, ValueError, AttributeError):
            pass
    # Only inspect the final component: an owner's name or parent folder is not model metadata.
    matches = re.findall(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([bm])\b", path.name.lower())
    if matches:
        sizes = [float(value) / (1000 if unit == "m" else 1) for value, unit in matches]
        size = max(sizes)
        if math.isfinite(size) and size > 0:
            return size, "model_name"
    return None, "unknown"


def estimate_memory(
    billions: float,
    *,
    quantization: str,
    precision: str,
    sequence_length: int,
    batch_size: int,
    rank: int,
    module_count: int,
    checkpointing: bool,
    optimizer: str,
) -> dict[str, float]:
    """GiB planning estimates, not measured peaks or a guarantee that a model fits.

    Coefficients are conservative planning heuristics. Architecture, attention kernels,
    quantization metadata, allocator behavior, and optimizer implementations vary.
    """
    bytes_per_weight = {"nf4": 0.65, "int8": 1.1, "none": 4 if precision == "fp32" else 2}
    weights = billions * 1e9 * bytes_per_weight[quantization] / 1024**3
    activations = (
        0.6 * billions * (sequence_length / 1024) * batch_size * (0.65 if checkpointing else 1)
    )
    adapters = 0.12 * billions * (rank / 16) * (module_count / 4)
    optimizer_memory = adapters * (1 if "8bit" in optimizer else 2)
    components = dict(
        weights=weights, activations=activations, adapters=adapters, optimizer=optimizer_memory
    )
    components["headroom"] = max(1.0, sum(components.values()) * 0.2)
    return {name: round(value, 3) for name, value in components.items()}
