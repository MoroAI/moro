import random
from pathlib import Path

from moro.core.errors import DatasetError
from moro.data.models import DatasetRow


def split_rows(
    rows: list[DatasetRow],
    validation_ratio: float = 0.1,
    eval_ratio: float = 0.1,
    seed: int = 42,
    group_by: str = "content",
) -> tuple[list[DatasetRow], list[DatasetRow], list[DatasetRow]]:
    """
    Split rows into (train, validation, eval) subsets.
    Deterministic given the same seed.

    Returns (train_rows, validation_rows, eval_rows).
    """
    if (
        not 0 <= validation_ratio < 1
        or not 0 <= eval_ratio < 1
        or validation_ratio + eval_ratio >= 1
    ):
        raise DatasetError("Split ratios must be nonnegative and sum to less than one.")
    required = 1 + int(validation_ratio > 0) + int(eval_ratio > 0)
    if rows and len(rows) < required:
        raise DatasetError(f"Need at least {required} rows for nonempty requested splits.")
    if not rows:
        return [], [], []

    from moro.data.clean import _near_hash

    groups = {}
    for row in rows:
        if group_by == "group_id":
            key = row.metadata.group_id
            if not key:
                raise DatasetError("Every row needs metadata.group_id for grouped splitting")
        elif group_by == "content":
            key = _near_hash(row)
        else:
            raise DatasetError("Unsupported split group key")
        groups.setdefault(key, []).append(row)
    if len(groups) < required:
        raise DatasetError(f"Need at least {required} independent groups for requested splits")
    # Source order cannot change group assignment. Whole groups stay together;
    # configured ratios apply to group counts, so row proportions can differ.
    shuffled = sorted(groups)
    random.Random(seed).shuffle(shuffled)
    count = len(shuffled)
    n_eval = max(1, int(count * eval_ratio)) if eval_ratio > 0 else 0
    n_val = max(1, int(count * validation_ratio)) if validation_ratio > 0 else 0

    def flatten(keys):
        return [row for key in keys for row in sorted(groups[key], key=lambda row: row.id)]

    return (
        flatten(shuffled[n_eval + n_val :]),
        flatten(shuffled[n_eval : n_eval + n_val]),
        flatten(shuffled[:n_eval]),
    )


def write_split(rows: list[DatasetRow], path: Path) -> None:
    """Write a list of DatasetRow objects to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(row.model_dump_json() + "\n")
