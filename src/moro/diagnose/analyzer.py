"""
Diagnostics engine — analyzes runs and recommends fixes.
"""

from __future__ import annotations

import re

KNOWN_ERRORS = [
    {
        "pattern": r"CUDA out of memory|OOM|out of memory",
        "issue": "GPU out of memory (OOM)",
        "cause": "Model + optimizer + activations exceed available VRAM.",
        "actions": [
            "Reduce `batch_size` to 1",
            "Increase `gradient_accumulation_steps` to 16 or 32",
            "Enable `gradient_checkpointing: true`",
            "Switch to `nf4` quantization",
            "Reduce `max_seq_length` (try 512)",
            "Use a smaller model (0.5B instead of 1.5B)",
        ],
        "config_changes": {
            "training.batch_size": 1,
            "training.gradient_accumulation_steps": 32,
            "training.gradient_checkpointing": True,
            "model.quantization": "nf4",
            "dataset.max_seq_length": 512,
        },
    },
    {
        "pattern": r"loss.*nan|nan.*loss|gradient.*nan",
        "issue": "NaN loss — training diverged",
        "cause": "Learning rate too high, or numeric instability in low precision.",
        "actions": [
            "Reduce `learning_rate` by 10× (e.g. 2e-5 instead of 2e-4)",
            "Switch `precision` to bf16 if CUDA supports it",
            "Reduce LoRA `r` rank (e.g. 8 instead of 16)",
            "Ensure dataset has no empty or malformed rows",
        ],
        "config_changes": {
            "training.learning_rate": 2e-5,
            "adapter.r": 8,
        },
    },
    {
        "pattern": r"No valid rows|dataset is empty|DatasetError",
        "issue": "Dataset pipeline failure",
        "cause": "Dataset source is missing, empty, or all rows were filtered out.",
        "actions": [
            "Run `moro data report` to inspect dataset quality",
            "Ensure `dataset.source` in moro.yaml points to a valid file",
            "Lower `min_quality_score` to 0.0",
            "Increase `max_seq_length` to include more rows",
            "Check that raw data uses a supported format (JSONL, CSV, TXT)",
        ],
        "config_changes": {
            "dataset.min_quality_score": 0.0,
        },
    },
    {
        "pattern": r"ImportError|ModuleNotFoundError",
        "issue": "Missing training dependency",
        "cause": "Required Python package is not installed.",
        "actions": [
            "Run: pip install 'moroai[train]'",
            "Verify torch is installed: python -c 'import torch; print(torch.__version__)'",
        ],
        "config_changes": {},
    },
]


def analyze_error(error_text: str) -> dict:
    """
    Match an error string against known patterns and return a diagnosis dict.
    Returns a generic unknown error dict if no pattern matches.
    """
    if not error_text:
        return {
            "issue": "No error recorded",
            "cause": "The run may have completed or been cancelled without an error.",
            "actions": ["Check run status with `moro runs list`"],
            "config_changes": {},
        }

    for entry in KNOWN_ERRORS:
        if re.search(entry["pattern"], error_text, re.IGNORECASE):
            return {
                "issue": entry["issue"],
                "cause": entry["cause"],
                "actions": entry["actions"],
                "config_changes": entry["config_changes"],
            }

    return {
        "issue": "Unknown error",
        "cause": error_text[:300],
        "actions": [
            "Check the full error in .moro/logs/",
            "Run `moro doctor` to verify the environment",
            "Try a smaller model or dataset first",
        ],
        "config_changes": {},
    }
