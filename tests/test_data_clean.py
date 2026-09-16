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
    # A row that passes (good quality)
    good = _make_row("How do I reset my password?", "Go to Settings and click Reset.", "row_good")
    valid, invalid, _, _ = clean_rows([good], min_quality_score=0.5)
    assert len(valid) == 1

    # A short row scores below the maximum threshold.
    short = _make_row("Hi", "Hello")
    valid2, invalid2, _, _ = clean_rows([short], min_quality_score=1.0)
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
    row = _make_row("How do I reset my password?", "Go to Settings and click Reset.")
    valid, invalid, _, _ = clean_rows([row], min_quality_score=1.0)
    assert len(valid) == 1
    assert not invalid
