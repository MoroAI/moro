"""Tests for quality scoring."""

from moro.data.models import DatasetMessage, DatasetRow
from moro.data.quality import approximate_token_count, score_row


def _make_row(messages: list[tuple[str, str]]) -> DatasetRow:
    return DatasetRow(
        id="test_row",
        source="test",
        messages=[DatasetMessage(role=role, content=content) for role, content in messages],
    )


def test_approximate_token_count_basic():
    row = _make_row([("user", "hello world"), ("assistant", "hi there friend")])
    count = approximate_token_count(row.messages)
    assert count > 0


def test_score_row_complete():
    row = _make_row(
        [
            ("user", "What is the capital of France?"),
            ("assistant", "The capital of France is Paris."),
        ]
    )
    score = score_row(row)
    assert 0.0 <= score <= 1.0
    assert score > 0.5  # reasonable quality


def test_score_row_missing_assistant_is_low():
    row = _make_row([("user", "only a question")])
    score = score_row(row)
    assert score < 0.5  # completeness penalty


def test_score_row_very_long_is_penalized():
    long_text = " ".join(["word"] * 10000)
    row = _make_row([("user", "question"), ("assistant", long_text)])
    score = score_row(row)
    assert score < 1.0  # length penalty applied


def test_score_row_repetitive_is_penalized():
    repetitive = " ".join(["the"] * 100)
    row = _make_row([("user", "test"), ("assistant", repetitive)])
    score = score_row(row)
    assert score < 0.8  # repetition penalty
