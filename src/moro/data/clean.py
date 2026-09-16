import json

from moro.core.hashing import sha256_text
from moro.data.models import DatasetRow, InvalidRow
from moro.data.quality import approximate_token_count, score_row


def clean_rows(
    rows: list[DatasetRow],
    max_seq_length: int = 1024,
    min_quality_score: float = 0.0,
    deduplicate: bool = True,
) -> tuple[list[DatasetRow], list[InvalidRow], int, int]:
    """
    Clean and optionally deduplicate rows.

    Returns:
        (valid_rows, invalid_rows, exact_dup_count, near_dup_count)
    """
    valid_rows: list[DatasetRow] = []
    invalid_rows: list[InvalidRow] = []

    seen_exact: set[str] = set()
    seen_near_hashes: set[str] = set()
    exact_dup_count = 0
    near_dup_count = 0

    for row in rows:
        # Compute token count and quality score
        token_count = approximate_token_count(row.messages)
        quality = score_row(row, token_count)
        row.token_count = token_count
        row.quality_score = quality

        # Empty messages check
        if not row.messages:
            invalid_rows.append(InvalidRow(source=row.source, reason="Row has no messages"))
            continue

        # Empty content check
        empty_msgs = [m for m in row.messages if not m.content.strip()]
        if empty_msgs:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=f"Message with empty content (role={empty_msgs[0].role})",
                )
            )
            continue

        # Max sequence length
        if token_count > max_seq_length:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=f"Token count {token_count} exceeds max_seq_length {max_seq_length}",
                )
            )
            continue

        # Minimum quality score filter
        if quality < min_quality_score:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=f"Quality score {quality:.4f} below minimum {min_quality_score}",
                )
            )
            continue

        if deduplicate:
            # Deduplicate message content independently of caller-supplied IDs.
            exact_key = sha256_text(json.dumps([m.model_dump() for m in row.messages]))
            if exact_key in seen_exact:
                exact_dup_count += 1
                continue
            seen_exact.add(exact_key)

            # Near-dedup using normalized text hash
            near_key = _near_hash(row)
            if near_key in seen_near_hashes:
                near_dup_count += 1
                continue
            seen_near_hashes.add(near_key)

        valid_rows.append(row)

    return valid_rows, invalid_rows, exact_dup_count, near_dup_count


def _near_hash(row: DatasetRow) -> str:
    """
    Create a normalized content hash for near-duplicate detection.
    Lowercases and strips extra whitespace before hashing.
    """
    text = json.dumps([[m.role, " ".join(m.content.lower().split())] for m in row.messages])
    return sha256_text(text)
