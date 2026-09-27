"""Tests for eval compare module."""

import pytest
from pathlib import Path

from moro.eval.compare import _compute_delta, compare_eval
from moro.eval.models import CaseScore, EvalResult, EvalSuite, EvalCase, EvalMessage, EvalExpect
from datetime import datetime, timezone


def _make_result(
    case_ids: list[str],
    passed: list[bool],
    scores: list[float],
    model: str = "base",
    suite_name: str = "test-suite",
    run_id: str | None = None,
) -> EvalResult:
    cases = [
        CaseScore(case_id=cid, passed=p, score=s)
        for cid, p, s in zip(case_ids, passed, scores)
    ]
    total = len(cases)
    pass_rate = sum(c.passed for c in cases) / total if total else 0.0
    avg_score = sum(c.score for c in cases) / total if total else 0.0
    return EvalResult(
        id=f"eval_{model}",
        suite_name=suite_name,
        run_id=run_id,
        model=model,
        created_at=datetime.now(timezone.utc),
        total_cases=total,
        pass_rate=round(pass_rate, 4),
        avg_score=round(avg_score, 4),
        fully_scored=True,
        execution_kind="stub",
        cases=cases,
    )


def test_compute_delta_improvement():
    base = _make_result(["c1", "c2"], [False, True], [0.3, 1.0])
    adapter = _make_result(["c1", "c2"], [True, True], [0.9, 1.0])

    delta = _compute_delta(base, adapter)

    assert delta["pass_rate_delta"] > 0
    assert delta["improved_cases"] == 1
    assert delta["regressed_cases"] == 0
    assert delta["summary"] in ("significant_improvement", "marginal_improvement")


def test_compute_delta_regression():
    base = _make_result(["c1", "c2"], [True, True], [1.0, 1.0])
    adapter = _make_result(["c1", "c2"], [False, True], [0.2, 1.0])

    delta = _compute_delta(base, adapter)

    assert delta["regressed_cases"] == 1
    assert delta["improved_cases"] == 0
    assert delta["summary"] == "regression_detected"


def test_compute_delta_no_change():
    base = _make_result(["c1"], [True], [1.0])
    adapter = _make_result(["c1"], [True], [1.0])

    delta = _compute_delta(base, adapter)

    assert delta["pass_rate_delta"] == 0.0
    assert delta["summary"] == "no_change"
    assert delta["improved_cases"] == 0
    assert delta["regressed_cases"] == 0


def test_compute_delta_all_cases_compared():
    base = _make_result(["c1", "c2", "c3"], [True, False, True], [1.0, 0.0, 0.8])
    adapter = _make_result(["c1", "c2", "c3"], [True, True, False], [1.0, 0.9, 0.1])

    delta = _compute_delta(base, adapter)

    assert delta["improved_cases"] == 1   # c2
    assert delta["regressed_cases"] == 1  # c3
    assert delta["unchanged_cases"] == 1  # c1
    assert len(delta["improvement_details"]) == 1
    assert delta["improvement_details"][0]["case_id"] == "c2"
    assert len(delta["regression_details"]) == 1
    assert delta["regression_details"][0]["case_id"] == "c3"


def test_compare_eval_with_stubs(tmp_path: Path):
    """Test compare_eval with stub responses — no model loading needed."""
    # Write a minimal eval suite
    suite_yaml = """\
name: stub-suite
version: "1"
cases:
  - id: c1
    messages:
      - role: user
        content: "Hello"
    expect:
      contains: ["Hello"]
  - id: c2
    messages:
      - role: user
        content: "Goodbye"
    expect:
      contains: ["Bye"]
"""
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(suite_yaml)

    # Base model misses c2, adapter gets both
    stub_base = {"c1": "Hello there!", "c2": "See you later"}
    stub_adapter = {"c1": "Hello friend!", "c2": "Bye, take care!"}

    base_result, adapter_result, delta = compare_eval(
        suite_path=suite_path,
        base_model="base-model",
        adapter_path="adapter-model",
        stub_base=stub_base,
        stub_adapter=stub_adapter,
        local_only=False,
    )

    assert base_result.pass_rate < adapter_result.pass_rate
    assert delta["improved_cases"] == 1
    assert delta["regressed_cases"] == 0


def test_compare_eval_stub_regression(tmp_path: Path):
    """Adapter regression is flagged."""
    suite_yaml = """\
name: reg-suite
version: "1"
cases:
  - id: r1
    messages:
      - role: user
        content: "Say yes"
    expect:
      contains: ["yes"]
"""
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(suite_yaml)

    stub_base = {"r1": "yes of course"}
    stub_adapter = {"r1": "no way"}

    base_result, adapter_result, delta = compare_eval(
        suite_path=suite_path,
        base_model="base",
        adapter_path="adapter",
        stub_base=stub_base,
        stub_adapter=stub_adapter,
        local_only=False,
    )

    assert base_result.pass_rate > adapter_result.pass_rate
    assert delta["regressed_cases"] == 1
    assert delta["summary"] == "regression_detected"
