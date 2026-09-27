"""
Baseline vs adapter comparison evaluation.

Runs the same eval suite against both the base model and a trained adapter,
then computes improvement/regression deltas per case and overall.
"""

from __future__ import annotations

from pathlib import Path

from moro.eval.models import EvalResult
from moro.eval.runner import run_suite


def compare_eval(
    suite_path: Path,
    base_model: str,
    adapter_path: str,
    *,
    run_id: str | None = None,
    max_samples: int | None = None,
    stub_base: dict | None = None,
    stub_adapter: dict | None = None,
    local_only: bool = True,
    revision: str | None = None,
) -> tuple[EvalResult, EvalResult, dict]:
    """
    Run eval suite on base and adapter, return (base_result, adapter_result, delta).

    Args:
        suite_path: Path to eval YAML.
        base_model: Base model name or path.
        adapter_path: Adapter path (PEFT adapter directory).
        run_id: Training run ID to bind adapter evidence.
        max_samples: Limit cases evaluated.
        stub_base: Optional stub responses for base (testing only).
        stub_adapter: Optional stub responses for adapter (testing only).

    Returns:
        Tuple of (base_result, adapter_result, delta_dict)
    """
    base_result = run_suite(
        suite_path=suite_path,
        model_path=base_model,
        run_id=None,
        max_samples=max_samples,
        stub_responses=stub_base,
        local_only=local_only,
        revision=revision,
    )

    adapter_result = run_suite(
        suite_path=suite_path,
        model_path=adapter_path,
        run_id=run_id,
        max_samples=max_samples,
        stub_responses=stub_adapter,
        local_only=local_only,
    )

    delta = _compute_delta(base_result, adapter_result)
    return base_result, adapter_result, delta


def _compute_delta(base: EvalResult, adapter: EvalResult) -> dict:
    """Compute per-case and aggregate deltas between base and adapter."""
    pass_rate_delta = round(adapter.pass_rate - base.pass_rate, 4)
    avg_score_delta = round(adapter.avg_score - base.avg_score, 4)

    # Per-case comparison (matched by case_id)
    base_by_id = {c.case_id: c for c in base.cases}
    adapter_by_id = {c.case_id: c for c in adapter.cases}
    case_deltas = []
    for case_id in adapter_by_id:
        base_case = base_by_id.get(case_id)
        adapter_case = adapter_by_id[case_id]
        if base_case is None:
            continue
        case_deltas.append({
            "case_id": case_id,
            "base_passed": base_case.passed,
            "adapter_passed": adapter_case.passed,
            "base_score": base_case.score,
            "adapter_score": adapter_case.score,
            "score_delta": round(adapter_case.score - base_case.score, 4),
            "regression": base_case.passed and not adapter_case.passed,
            "improvement": not base_case.passed and adapter_case.passed,
        })

    regressions = [c for c in case_deltas if c["regression"]]
    improvements = [c for c in case_deltas if c["improvement"]]

    return {
        "pass_rate_base": base.pass_rate,
        "pass_rate_adapter": adapter.pass_rate,
        "pass_rate_delta": pass_rate_delta,
        "avg_score_base": base.avg_score,
        "avg_score_adapter": adapter.avg_score,
        "avg_score_delta": avg_score_delta,
        "improved_cases": len(improvements),
        "regressed_cases": len(regressions),
        "unchanged_cases": len(case_deltas) - len(improvements) - len(regressions),
        "regression_details": regressions,
        "improvement_details": improvements,
        "summary": _summarize_delta(pass_rate_delta, regressions),
    }


def _summarize_delta(pass_rate_delta: float, regressions: list) -> str:
    if pass_rate_delta > 0.05:
        return "significant_improvement"
    elif pass_rate_delta > 0:
        return "marginal_improvement"
    elif pass_rate_delta == 0 and not regressions:
        return "no_change"
    elif regressions:
        return "regression_detected"
    else:
        return "marginal_regression"
