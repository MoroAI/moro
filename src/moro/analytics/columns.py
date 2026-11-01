"""Closed public-name to SQL-column mappings; values are never SQL fragments."""

from types import MappingProxyType


class AnalyticsColumnError(ValueError):
    """The caller requested a column outside the public analytics contract."""


HYPERPARAM_COLUMNS = MappingProxyType(
    {
        "learning_rate": "learning_rate",
        "batch_size": "batch_size",
        "gradient_accumulation_steps": "gradient_accumulation_steps",
        "epochs": "epochs",
        "warmup_ratio": "warmup_ratio",
        "weight_decay": "weight_decay",
        "lora_r": "lora_r",
        "lora_alpha": "lora_alpha",
        "lora_dropout": "lora_dropout",
        "max_seq_length": "max_seq_length",
    }
)
EXPERIMENT_METRIC_COLUMNS = MappingProxyType(
    {
        "eval_delta": "eval_delta",
        "eval_pass_rate": "eval_pass_rate",
        "final_train_loss": "final_train_loss",
        "final_eval_loss": "final_eval_loss",
        "duration_seconds": "duration_seconds",
        "peak_vram_gb": "peak_vram_gb",
        "total_steps": "total_steps",
        "tokens_per_second": "tokens_per_second",
    }
)


def resolve_hyperparam(value: str) -> str:
    if type(value) is not str or value not in HYPERPARAM_COLUMNS:
        raise AnalyticsColumnError("Unsupported analytics hyperparameter")
    return HYPERPARAM_COLUMNS[value]


def resolve_metric(value: str) -> str:
    if type(value) is not str or value not in EXPERIMENT_METRIC_COLUMNS:
        raise AnalyticsColumnError("Unsupported analytics metric")
    return EXPERIMENT_METRIC_COLUMNS[value]
