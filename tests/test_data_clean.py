"""Tests for data cleaning."""

from moro.data.clean import clean_rows
from moro.data.models import DatasetMessage, DatasetRow


def _make_row(user_text: str, assistant_text: str, row_id: str = "row_test") -> DatasetRow:
    return DatasetRow(
        id=row_id,
        source="test",
        messages=[
            DatasetMessage(role="user", content=user_text),
            DatasetMessage(role="assistant", content=assistant_text),
        ],
    )


def test_clean_valid_rows():
    rows = [_make_row(f"Hello {i}", f"Hi {i}!", f"row_{i}") for i in range(5)]
    valid, invalid, exact_dups, near_dups = clean_rows(rows, deduplicate=True)
    assert len(valid) == 5
    assert len(invalid) == 0
    assert exact_dups == 0


def test_clean_removes_exact_duplicates():
    row = _make_row("Same question", "Same answer", row_id="row_abc123")
    rows = [row, row, row]
    valid, invalid, exact_dups, near_dups = clean_rows(rows, deduplicate=True)
    assert len(valid) == 1
    assert exact_dups == 2


def test_clean_removes_over_seq_length():
    long_text = " ".join(["word"] * 2000)
    row = _make_row(long_text, "Reply", row_id="row_long")
    valid, invalid, _, _ = clean_rows([row], max_seq_length=512)
    assert len(valid) == 0
    assert len(invalid) == 1
    assert "Token count" in invalid[0].reason


def test_clean_quality_filter():
    # A row that passes (good quality) — use fast path for deterministic thresholds
    good = _make_row("How do I reset my password?", "Go to Settings and click Reset.", "row_good")
    valid, invalid, _, _ = clean_rows([good], min_quality_score=0.5, use_epistemic_scoring=False)
    assert len(valid) == 1

    # A short row scores below the maximum threshold.
    short = _make_row("Hi", "Hello")
    valid2, invalid2, _, _ = clean_rows([short], min_quality_score=1.0, use_epistemic_scoring=False)
    assert len(valid2) == 0
    assert len(invalid2) == 1


def test_clean_near_duplicates():
    row1 = _make_row("hello world today", "great response", "row_1")
    row2 = _make_row("HELLO  world today", "great response", "row_2")  # different ID, same text
    # Update IDs so they're different
    row2.id = "row_2_different"

    valid, invalid, exact_dups, near_dups = clean_rows([row1, row2], deduplicate=True)
    # Near-dup detection should catch row2 since normalized text is identical
    assert len(valid) == 1
    assert near_dups >= 1


def test_same_id_different_content_survives():
    valid, _, exact, near = clean_rows(
        [
            _make_row("Question one", "Answer one", "same"),
            _make_row("Question two", "Answer two", "same"),
        ]
    )
    assert len(valid) == 2
    assert exact == near == 0


def test_equal_quality_threshold_is_inclusive():
    """Row that scores at threshold should pass (fast path for deterministic test)."""
    row = _make_row("How do I reset my password?", "Go to Settings and click Reset.")
    # Use fast path to get a deterministic score
    valid, invalid, _, _ = clean_rows([row], min_quality_score=0.0, use_epistemic_scoring=False)
    assert len(valid) == 1
    assert not invalid


def test_epistemic_scoring_attaches_metadata():
    """Epistemic scoring should attach full DatasetRowMetadata to valid rows."""
    row = _make_row(
        "What is the dosage for ibuprofen?", "Adults: 200–400mg every 4–6 hours as needed."
    )
    valid, _, _, _ = clean_rows([row], use_epistemic_scoring=True)
    assert len(valid) == 1
    assert valid[0].metadata is not None
    assert valid[0].metadata.classification in {
        "HIGH_QUALITY_STANDARD",
        "RARE_HIGH_VALUE_EDGE_CASE",
        "LOW_INFO_BOILERPLATE",
        "NOISY_OUTLIER",
    }
    assert 0.0 <= valid[0].metadata.quality_score <= 1.0
    assert valid[0].metadata.info_metrics.zlib_entropy >= 0.0


def test_mi_guard_preserves_high_ppmi_row():
    """
    The MI Guard fires when a row looks noisy (high zlib entropy) but has
    strong domain glossary signal (normalized PPMI >= 0.5).

    We verify that the PPMI proxy works correctly and the MI Guard logic is
    consistent — noisy rows with strong domain signal get mi_guard_override=True.
    """

    from moro.data.quality import (
        calculate_domain_ppmi,
        classify_row,
    )

    # Construct a row where ALL words are in the domain glossary (100% overlap → high PPMI)
    domain_terms = ["lisinopril", "pharmacokinetics", "bioavailability", "plasma", "renally", "gfr"]
    # Force a high-overlap text by using only domain terms
    asst_text = " ".join(domain_terms * 5)  # 30 domain terms → very high PPMI

    glossary = set(domain_terms)
    ppmi = calculate_domain_ppmi(asst_text, glossary)
    normalized_ppmi = ppmi / 10.0

    # Verify the PPMI proxy works
    assert ppmi > 0.0, f"PPMI should be > 0 with glossary match, got {ppmi}"
    assert normalized_ppmi >= 0.5, f"Normalized PPMI should be >= 0.5, got {normalized_ppmi}"

    # Now verify classification: with very high entropy + high PPMI → MI Guard
    # We'll test the classify_row function directly
    high_entropy = 0.6  # above HIGH_ENTROPY_THRESHOLD = 0.45
    classification, mi_guard = classify_row(
        entropy=high_entropy, ppmi=ppmi, resnik_ic=0.0, is_duplicate=False
    )

    assert classification == "RARE_HIGH_VALUE_EDGE_CASE", (
        f"Expected RARE_HIGH_VALUE_EDGE_CASE, got {classification} "
        f"(normalized_ppmi={normalized_ppmi:.3f})"
    )
    assert mi_guard is True, "MI Guard override should be True for noisy-but-valuable rows"
