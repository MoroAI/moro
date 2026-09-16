"""
Eval scorers — deterministic checkers for EvalExpect conditions.
"""

from __future__ import annotations

import re

from moro.eval.models import CaseScore, EvalCase


def score_case(case: EvalCase, response: str) -> CaseScore:
    """
    Score a single eval case against the model's response.

    Returns a CaseScore with passed=True if ALL expect conditions pass.
    If no expect is defined, the case passes by default (it is a generation-only case).
    """
    if case.expect is None:
        return CaseScore(
            case_id=case.id,
            passed=True,
            score=1.0,
            response=response,
            details={"note": "no expect conditions defined"},
        )

    details: dict[str, object] = {}
    checks: list[bool] = []

    # contains — all must appear
    if case.expect.contains:
        results = {term: term in response for term in case.expect.contains}
        passed = all(results.values())
        details["contains"] = results
        checks.append(passed)

    # any_of_contains — at least one must appear
    if case.expect.any_of_contains:
        results = {term: term in response for term in case.expect.any_of_contains}
        passed = any(results.values())
        details["any_of_contains"] = results
        checks.append(passed)

    # regex — all patterns must match
    if case.expect.regex:
        results = {}
        for pattern in case.expect.regex:
            try:
                matched = bool(re.search(pattern, response))
            except re.error:
                matched = False
            results[pattern] = matched
        passed = all(results.values())
        details["regex"] = results
        checks.append(passed)

    # json_schema — attempt to parse response as JSON and validate
    if case.expect.json_schema:
        try:
            import json

            import jsonschema

            parsed = json.loads(response)
            jsonschema.validate(parsed, case.expect.json_schema)
            details["json_schema"] = "passed"
            checks.append(True)
        except Exception as exc:
            details["json_schema"] = str(exc)
            checks.append(False)

    overall_passed = all(checks) if checks else True
    score = 1.0 if overall_passed else (sum(checks) / len(checks) if checks else 0.0)

    return CaseScore(
        case_id=case.id,
        passed=overall_passed,
        score=round(score, 4),
        response=response,
        details=details,  # type: ignore[arg-type]
    )
