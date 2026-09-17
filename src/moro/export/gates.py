"""Fail-closed release checks against recorded, artifact-bound evaluations."""

import json
from pathlib import Path

from moro.config.models import MoroConfig
from moro.core.errors import DependencyError, EvalError, ExportError
from moro.core.hashing import sha256_directory, sha256_file
from moro.eval.loader import load_suite
from moro.eval.models import EvalResult
from moro.export.eligibility import ExportRun
from moro.storage import db


def check_release_requirements(root: Path, run: ExportRun, current: MoroConfig) -> dict:
    """Enforce both saved and current policies; never silently weaken either."""
    evidence = {}
    policies = []
    fingerprint = sha256_directory(run.adapter_path)
    for config in (run.config, current):
        policy = config.release.require
        if policy is None:
            continue
        policies.append(policy.model_dump(mode="json"))
        if policy.min_improvement is not None or policy.max_regression is not None:
            raise ExportError(
                "Release blocked: improvement/regression requirements need baseline comparison "
                "evidence, which is not implemented yet."
            )
        if not (policy.eval_suite or policy.safety_pass or policy.min_pass_rate is not None):
            continue
        suites = []
        try:
            for ref in config.eval.suites:
                path = ref.path if ref.path.is_absolute() else root / ref.path
                suite = load_suite(path)
                if policy.eval_suite is None or suite.name == policy.eval_suite:
                    suites.append((path, suite))
        except (EvalError, DependencyError, OSError) as exc:
            raise ExportError(f"Release blocked: cannot validate required suite: {exc}") from exc
        if not suites:
            raise ExportError("Release blocked: required suite must be listed in eval.suites.")
        names = [suite.name for _, suite in suites]
        if len(set(names)) != len(names):
            raise ExportError("Release blocked: configured suite names must be unique.")
        safety_count = 0
        conn = db.get_connection(root)
        try:
            for path, suite in suites:
                row = conn.execute(
                    "SELECT * FROM eval_runs WHERE run_id = ? AND suite_name = ? "
                    "ORDER BY created_at DESC, id DESC LIMIT 1",
                    (run.id, suite.name),
                ).fetchone()
                if row is None:
                    raise ExportError(f"Release blocked: no evaluation for suite {suite.name}.")
                try:
                    result = EvalResult.model_validate_json(row["result_json"])
                except ValueError as exc:
                    raise ExportError(
                        "Release blocked: invalid stored evaluation; rerun it."
                    ) from exc
                if (
                    result.id != row["id"]
                    or result.run_id != run.id
                    or result.suite_name != suite.name
                    or result.execution_kind != "model"
                    or not result.fully_scored
                    or result.adapter_sha256 != fingerprint
                    or result.suite_sha256 != sha256_file(path)
                ):
                    raise ExportError(
                        f"Release blocked: invalid or stale evidence for {suite.name}. "
                        "Rerun the full suite against this adapter."
                    )
                if [s.case_id for s in result.cases] != [c.id for c in suite.cases]:
                    raise ExportError("Release blocked: evaluation must cover every suite case.")
                if not result.cases or result.total_cases != len(result.cases):
                    raise ExportError("Release blocked: inconsistent evaluation case counts.")
                rate = sum(s.passed for s in result.cases) / len(result.cases)
                if round(rate, 4) != result.pass_rate:
                    raise ExportError("Release blocked: inconsistent evaluation pass rate.")
                threshold = policy.min_pass_rate if policy.min_pass_rate is not None else 1.0
                if rate < threshold:
                    raise ExportError(
                        f"Release blocked: {suite.name} pass rate {rate:.4f} "
                        f"is below {threshold:.4f}."
                    )
                for case, score in zip(suite.cases, result.cases):
                    if case.expect is None:
                        raise ExportError(
                            "Release blocked: generation-only cases are not quality evidence."
                        )
                    if "safety" in case.tags:
                        safety_count += 1
                        if policy.safety_pass and not score.passed:
                            raise ExportError(f"Release blocked: safety case {case.id} failed.")
                evidence[result.id] = {
                    "eval_id": result.id,
                    "suite": suite.name,
                    "suite_sha256": result.suite_sha256,
                    "pass_rate": result.pass_rate,
                }
        finally:
            conn.close()
        if policy.safety_pass and safety_count == 0:
            raise ExportError(
                "Release blocked: safety_pass requires evaluated cases tagged 'safety'."
            )
    return {
        "status": "passed" if evidence else "not_required",
        "adapter_sha256": fingerprint,
        "policies": policies,
        "evaluations": list(evidence.values()),
    }


def write_gate_report(report: dict, directory: Path) -> None:
    (directory / "release_gate.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
