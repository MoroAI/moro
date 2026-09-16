import statistics

from moro.data.models import DatasetRow, DatasetStats


def compute_stats(
    rows: list[DatasetRow],
    invalid_count: int = 0,
    exact_dup_count: int = 0,
    near_dup_count: int = 0,
    train_rows: int = 0,
    validation_rows: int = 0,
    eval_rows: int = 0,
    pii_scan: bool = False,
) -> DatasetStats:
    """Compute aggregate statistics across a list of valid DatasetRows."""
    if not rows:
        return DatasetStats(
            rows_total=invalid_count,
            rows_invalid=invalid_count,
            rows_deduplicated=exact_dup_count,
            rows_near_duplicate=near_dup_count,
        )

    token_counts = [r.token_count for r in rows]
    quality_scores = [r.quality_score for r in rows]
    privacy_warning_count = sum(1 for r in rows if r.privacy_flags)
    warnings: list[str] = []

    sorted_tokens = sorted(token_counts)
    p50_idx = len(sorted_tokens) // 2
    p95_idx = int(len(sorted_tokens) * 0.95)

    if privacy_warning_count > 0 and pii_scan:
        warnings.append(
            f"{privacy_warning_count} rows have possible PII/secrets — review before training."
        )

    if exact_dup_count > 0:
        warnings.append(f"{exact_dup_count} exact duplicate rows removed.")

    if near_dup_count > 0:
        warnings.append(f"{near_dup_count} near-duplicate rows removed.")

    sorted_quality = sorted(quality_scores)
    q_p50_idx = len(sorted_quality) // 2

    return DatasetStats(
        rows_total=len(rows) + invalid_count + exact_dup_count + near_dup_count,
        rows_valid=len(rows),
        rows_invalid=invalid_count,
        rows_deduplicated=exact_dup_count,
        rows_near_duplicate=near_dup_count,
        train_rows=train_rows,
        validation_rows=validation_rows,
        eval_rows=eval_rows,
        avg_tokens=round(statistics.mean(token_counts), 1),
        p50_tokens=float(sorted_tokens[p50_idx]) if sorted_tokens else 0.0,
        p95_tokens=float(sorted_tokens[min(p95_idx, len(sorted_tokens) - 1)]),
        max_tokens=max(token_counts),
        avg_quality_score=round(statistics.mean(quality_scores), 4),
        min_quality_score=round(min(quality_scores), 4),
        quality_score_p50=round(float(sorted_quality[q_p50_idx]), 4),
        privacy_warning_count=privacy_warning_count,
        warnings=warnings,
    )
