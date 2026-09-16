import random
from pathlib import Path

from moro.data.models import DatasetRow


def split_rows(
    rows: list[DatasetRow],
    validation_ratio: float = 0.1,
    eval_ratio: float = 0.1,
    seed: int = 42,
) -> tuple[list[DatasetRow], list[DatasetRow], list[DatasetRow]]:
    """
    Split rows into (train, validation, eval) subsets.
    Deterministic given the same seed.

    Returns (train_rows, validation_rows, eval_rows).
    """
    if not rows:
        return [], [], []

    rng = random.Random(seed)
    shuffled = list(rows)
    rng.shuffle(shuffled)

    n = len(shuffled)
    n_eval = max(1, int(n * eval_ratio)) if eval_ratio > 0 else 0
    n_val = max(1, int(n * validation_ratio)) if validation_ratio > 0 else 0

    # Ensure we don't exceed total
    n_eval = min(n_eval, n)
    n_val = min(n_val, n - n_eval)

    eval_rows = shuffled[:n_eval]
    validation_rows = shuffled[n_eval : n_eval + n_val]
    train_rows = shuffled[n_eval + n_val :]

    return train_rows, validation_rows, eval_rows


def write_split(rows: list[DatasetRow], path: Path) -> None:
    """Write a list of DatasetRow objects to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.model_dump_json() + "\n")
