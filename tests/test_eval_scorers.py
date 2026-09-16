"""Tests for eval scorers."""

from moro.eval.models import EvalCase, EvalExpect, EvalMessage
from moro.eval.scorers import score_case


def _make_case(
    case_id: str,
    expect: EvalExpect | None = None,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        messages=[EvalMessage(role="user", content="Test question")],
        expect=expect,
    )


def test_contains_passes():
    case = _make_case("c1", EvalExpect(contains=["Settings", "Security"]))
    score = score_case(case, "Go to Settings > Security and reset your password.")
    assert score.passed is True
    assert score.score == 1.0


def test_contains_fails_missing():
    case = _make_case("c1", EvalExpect(contains=["Settings", "Security"]))
    score = score_case(case, "Just click reset.")
    assert score.passed is False


def test_any_of_contains_passes():
    case = _make_case("c2", EvalExpect(any_of_contains=["refund", "14 days"]))
    score = score_case(case, "We offer a refund within the return window.")
    assert score.passed is True


def test_any_of_contains_fails():
    case = _make_case("c2", EvalExpect(any_of_contains=["refund", "14 days"]))
    score = score_case(case, "No returns accepted.")
    assert score.passed is False


def test_regex_passes():
    case = _make_case("c3", EvalExpect(regex=[r"\d+ days"]))
    score = score_case(case, "You have 30 days to return the item.")
    assert score.passed is True


def test_regex_fails():
    case = _make_case("c3", EvalExpect(regex=[r"\d+ days"]))
    score = score_case(case, "No time limit mentioned.")
    assert score.passed is False


def test_no_expect_always_passes():
    case = _make_case("c4", expect=None)
    score = score_case(case, "Anything at all.")
    assert score.passed is True
    assert score.score == 1.0


def test_multiple_conditions_all_must_pass():
    case = _make_case(
        "c5",
        EvalExpect(
            contains=["Settings"],
            any_of_contains=["password", "reset"],
        ),
    )
    score = score_case(case, "Go to Settings to reset your password.")
    assert score.passed is True

    score2 = score_case(case, "Go to Settings only.")
    assert score2.passed is False  # any_of_contains fails
