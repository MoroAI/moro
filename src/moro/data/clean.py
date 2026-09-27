"""
MoroAI Data Cleaner — Epistemic Edition.

Integrates the MI Guard: rows classified as RARE_HIGH_VALUE_EDGE_CASE with
mi_guard_override=True are preserved even when they fail basic quality thresholds,
because they contain rare, high-value domain facts that standard heuristics
would incorrectly discard.

Pipeline:
  1. Structural validation (roles, empty content, length)
  2. Global stats first-pass (build token frequency map for Resnik IC)
  3. Exact + near deduplication
  4. Full epistemic scoring (zlib entropy, PPMI, Resnik IC, MI Guard)
  5. Quality filter — bypassed for mi_guard_override rows
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from moro.core.hashing import sha256_text
from moro.data.models import DatasetRow, InvalidRow
from moro.data.quality import (
    approximate_token_count,
    score_row,
    score_row_epistemic,
)

# ──────────────────────────────────────────────────────────────────────────────
# Global Stats First-Pass
# ──────────────────────────────────────────────────────────────────────────────

def _build_global_stats(rows: list[DatasetRow]) -> tuple[Counter, int]:
    """
    First pass over all rows to build global token frequency map.
    Required for Resnik IC (IDF of rarest token per row).
    """
    counts: Counter = Counter()
    for row in rows:
        text = " ".join(msg.content for msg in row.messages).lower()
        counts.update(text.split())
    return counts, len(rows)


def _load_domain_glossary(glossary_path: Path | None) -> set[str]:
    """
    Load domain glossary from a plain-text file (one term per line).
    If no glossary is provided, returns an empty set (PPMI = 0 for all rows).
    """
    if not glossary_path or not glossary_path.exists():
        return set()
    terms: set[str] = set()
    with glossary_path.open("r", encoding="utf-8") as f:
        for line in f:
            term = line.strip().lower()
            if term and not term.startswith("#"):
                terms.add(term)
    return terms


# ──────────────────────────────────────────────────────────────────────────────
# Near-Duplicate Hashing
# ──────────────────────────────────────────────────────────────────────────────

def _near_hash(row: DatasetRow) -> str:
    """
    Normalized content hash for near-duplicate detection.
    Lowercases and strips extra whitespace before hashing.
    """
    text = json.dumps(
        [[m.role, " ".join(m.content.lower().split())] for m in row.messages]
    )
    return sha256_text(text)


# ──────────────────────────────────────────────────────────────────────────────
# Main Clean Pipeline
# ──────────────────────────────────────────────────────────────────────────────

def clean_rows(
    rows: list[DatasetRow],
    max_seq_length: int = 1024,
    min_quality_score: float = 0.0,
    deduplicate: bool = True,
    domain_glossary_path: Path | None = None,
    use_epistemic_scoring: bool = True,
) -> tuple[list[DatasetRow], list[InvalidRow], int, int]:
    """
    Clean, score (epistemically), and deduplicate rows.

    The MI Guard (in score_row_epistemic) will preserve rows classified as
    RARE_HIGH_VALUE_EDGE_CASE even when min_quality_score would reject them,
    because they contain rare, high-value domain information.

    Args:
        rows: Input dataset rows.
        max_seq_length: Hard cap on token count (not overrideable by MI Guard).
        min_quality_score: Minimum quality score — bypassed for mi_guard_override rows.
        deduplicate: Whether to apply exact + near deduplication.
        domain_glossary_path: Path to a plain-text domain glossary for PPMI calculation.
        use_epistemic_scoring: If True, runs full IT scoring. If False, uses fast path.

    Returns:
        (valid_rows, invalid_rows, exact_dup_count, near_dup_count)
    """
    valid_rows: list[DatasetRow] = []
    invalid_rows: list[InvalidRow] = []

    seen_exact: set[str] = set()
    seen_near_hashes: set[str] = set()
    exact_dup_count = 0
    near_dup_count = 0

    # Load domain glossary
    domain_glossary = _load_domain_glossary(domain_glossary_path)

    # First-pass: build global stats for Resnik IC
    global_token_counts, total_docs = (
        _build_global_stats(rows) if use_epistemic_scoring else (Counter(), 0)
    )

    for row in rows:
        # ── Step 1: Structural validation ────────────────────────────────────

        if not row.messages:
            invalid_rows.append(InvalidRow(source=row.source, reason="Row has no messages"))
            continue

        empty_msgs = [m for m in row.messages if not m.content.strip()]
        if empty_msgs:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=f"Message with empty content (role={empty_msgs[0].role})",
                )
            )
            continue

        roles = {m.role for m in row.messages}
        if not {"user", "assistant"} <= roles or row.messages[-1].role != "assistant":
            invalid_rows.append(
                InvalidRow(source=row.source, reason="Conversation needs user and final assistant turn")
            )
            continue

        # ── Step 2: Token count (always needed) ─────────────────────────────
        token_count = approximate_token_count(row.messages)
        row.token_count = token_count

        # Hard cap — not overrideable even by MI Guard
        if token_count > max_seq_length:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=f"Token count {token_count} exceeds max_seq_length {max_seq_length}",
                )
            )
            continue

        # ── Step 3: Deduplication ────────────────────────────────────────────
        is_duplicate = False
        if deduplicate:
            exact_key = sha256_text(json.dumps([m.model_dump() for m in row.messages]))
            if exact_key in seen_exact:
                exact_dup_count += 1
                is_duplicate = True
            else:
                seen_exact.add(exact_key)

                near_key = _near_hash(row)
                if near_key in seen_near_hashes:
                    near_dup_count += 1
                    is_duplicate = True
                else:
                    seen_near_hashes.add(near_key)

            if is_duplicate:
                invalid_rows.append(
                    InvalidRow(source=row.source, reason="duplicate")
                )
                continue

        # ── Step 4: Epistemic scoring ────────────────────────────────────────
        if use_epistemic_scoring:
            metadata = score_row_epistemic(
                row=row,
                domain_glossary=domain_glossary,
                global_token_counts=global_token_counts,
                total_docs=total_docs,
                is_duplicate=is_duplicate,
            )
            row.metadata = metadata
            row.quality_score = metadata.quality_score
            row.privacy_flags = metadata.privacy_flags
        else:
            # Fast path (backward compat)
            quality = score_row(row, token_count)
            row.quality_score = quality

        quality = row.quality_score
        mi_guard = row.metadata.mi_guard_override if use_epistemic_scoring else False
        classification = row.metadata.classification if use_epistemic_scoring else "HIGH_QUALITY_STANDARD"

        # ── Step 5: Quality filter (respects MI Guard) ───────────────────────
        if quality < min_quality_score and not mi_guard:
            invalid_rows.append(
                InvalidRow(
                    source=row.source,
                    reason=(
                        f"Quality score {quality:.4f} below minimum {min_quality_score} "
                        f"[{classification}]"
                    ),
                )
            )
            continue

        valid_rows.append(row)

    return valid_rows, invalid_rows, exact_dup_count, near_dup_count
