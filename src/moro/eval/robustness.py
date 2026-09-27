"""
MoroAI Robustness Scorer.

Computes robustness metrics by comparing a model's base (pristine) performance
against its performance on adversarially perturbed inputs.

A Robustness Score of 1.0 means the model's answers were completely unchanged
by all perturbations — the model genuinely understands the domain.
A Robustness Score of 0.0 means every perturbation caused the model to fail.

Two robustness metrics:
  - raw_robustness: % of perturbed cases that passed (regardless of base outcome)
  - strict_robustness: % of perturbed cases that matched the base outcome exactly
    (correctly passed if base passed, correctly failed if base failed)

Vulnerabilities count cases where the base passed but a perturbation caused failure
— these are the regressions that matter most in production.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CaseRobustnessResult:
    """Robustness metrics for a single eval case."""
    case_id: str
    base_passed: bool
    perturbed_results: dict[str, bool]  # perturbation_type → passed

    # Computed fields
    raw_robustness: float = 0.0
    strict_robustness: float = 0.0
    vulnerability_count: int = 0
    failed_perturbations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.perturbed_results:
            self.raw_robustness = 1.0
            self.strict_robustness = 1.0
            return

        total = len(self.perturbed_results)
        passed_count = sum(1 for p in self.perturbed_results.values() if p)
        strict_count = sum(
            1 for p in self.perturbed_results.values() if p == self.base_passed
        )
        vulns = [
            ptype
            for ptype, p in self.perturbed_results.items()
            if self.base_passed and not p
        ]

        self.raw_robustness = round(passed_count / total, 4)
        self.strict_robustness = round(strict_count / total, 4)
        self.vulnerability_count = len(vulns)
        self.failed_perturbations = vulns


@dataclass
class RobustnessReport:
    """Aggregate robustness report across all eval cases."""
    total_cases: int
    case_results: list[CaseRobustnessResult]

    # Aggregate metrics
    avg_raw_robustness: float = 0.0
    avg_strict_robustness: float = 0.0
    total_vulnerabilities: int = 0
    most_vulnerable_perturbation: str | None = None

    # Per-perturbation type failure counts
    perturbation_failure_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.case_results:
            return

        n = len(self.case_results)
        self.avg_raw_robustness = round(
            sum(r.raw_robustness for r in self.case_results) / n, 4
        )
        self.avg_strict_robustness = round(
            sum(r.strict_robustness for r in self.case_results) / n, 4
        )
        self.total_vulnerabilities = sum(
            r.vulnerability_count for r in self.case_results
        )

        # Count failures per perturbation type
        for result in self.case_results:
            for ptype in result.failed_perturbations:
                self.perturbation_failure_counts[ptype] = (
                    self.perturbation_failure_counts.get(ptype, 0) + 1
                )

        if self.perturbation_failure_counts:
            self.most_vulnerable_perturbation = max(
                self.perturbation_failure_counts, key=self.perturbation_failure_counts.get
            )

    @property
    def robustness_grade(self) -> str:
        """Letter grade for the robustness score."""
        s = self.avg_strict_robustness
        if s >= 0.95:
            return "A (Excellent)"
        if s >= 0.85:
            return "B (Good)"
        if s >= 0.70:
            return "C (Fair)"
        if s >= 0.55:
            return "D (Poor)"
        return "F (Fragile)"


def compute_case_robustness(
    case_id: str,
    base_passed: bool,
    perturbed_results: dict[str, bool],
) -> CaseRobustnessResult:
    """
    Compute robustness metrics for a single eval case.

    Args:
        case_id: Unique identifier for the eval case.
        base_passed: Whether the model passed on the original, pristine input.
        perturbed_results: Dict mapping perturbation_type → passed (bool).

    Returns:
        CaseRobustnessResult with computed metrics.
    """
    return CaseRobustnessResult(
        case_id=case_id,
        base_passed=base_passed,
        perturbed_results=perturbed_results,
    )


def compute_robustness_report(
    case_results: list[CaseRobustnessResult],
) -> RobustnessReport:
    """
    Aggregate per-case robustness results into a report.

    Args:
        case_results: List of per-case robustness results.

    Returns:
        RobustnessReport with aggregate metrics and grades.
    """
    return RobustnessReport(
        total_cases=len(case_results),
        case_results=case_results,
    )


def compute_robustness_score(
    base_passed: bool,
    perturbed_results: dict[str, bool],
) -> dict[str, float]:
    """
    Compute robustness metrics for a single case (simple dict API).

    Backward-compatible API for the CLI runner.

    Returns:
        {
            "raw_robustness": float,
            "strict_robustness": float,
            "vulnerability_count": int
        }
    """
    result = CaseRobustnessResult(
        case_id="_",
        base_passed=base_passed,
        perturbed_results=perturbed_results,
    )
    return {
        "raw_robustness": result.raw_robustness,
        "strict_robustness": result.strict_robustness,
        "vulnerability_count": result.vulnerability_count,
    }


def create_perturbed_suite(
    suite_path: Path,
    output_path: Path,
    seed: int = 42,
    max_samples: int | None = None,
) -> None:
    """
    Generate an adversarial eval suite with deterministic perturbations.
    """
    import yaml

    from moro.eval.loader import load_suite
    from moro.eval.perturbations import PerturbationEngine

    suite = load_suite(suite_path)
    engine = PerturbationEngine(seed=seed)
    cases = suite.cases[:max_samples] if max_samples else suite.cases

    new_cases: list[dict] = []
    for case in cases:
        # Original
        new_cases.append(case.model_dump(mode="json"))

        # Find user message
        user_msg_idx = -1
        for i, m in enumerate(case.messages):
            if m.role == "user":
                user_msg_idx = i

        if user_msg_idx >= 0:
            orig_text = case.messages[user_msg_idx].content
            perturbed = engine.generate_perturbations(orig_text)
            for ptype in ["distractor_injection", "typo_noise", "negation_constraint", "entity_swap"]:
                p_text = perturbed[ptype]
                case_dict = case.model_dump(mode="json")
                case_dict["id"] = f"{case.id}_{ptype}"
                case_dict["messages"][user_msg_idx]["content"] = p_text
                new_cases.append(case_dict)

    data = {
        "name": f"{suite.name}_perturbed",
        "description": f"Adversarially perturbed variation of {suite.name} (seed={seed})",
        "cases": new_cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False)


def evaluate_robustness(
    suite_path: Path,
    model_path: str | None = None,
    seed: int = 42,
    max_samples: int | None = None,
    stub_responses: dict[str, str] | None = None,
    local_only: bool = True,
    revision: str | None = None,
) -> RobustnessReport:
    """
    Run adversarial perturbation testing on an eval suite.
    """
    from moro.eval.loader import load_suite
    from moro.eval.models import EvalCase, EvalMessage
    from moro.eval.perturbations import PerturbationEngine
    from moro.eval.runner import _generate_response, _load_generator
    from moro.eval.scorers import score_case

    suite = load_suite(suite_path)
    engine = PerturbationEngine(seed=seed)
    cases = suite.cases[:max_samples] if max_samples else suite.cases

    generator = None
    if stub_responses is None and model_path is not None:
        generator = _load_generator(model_path, local_only=local_only, revision=revision)

    results: list[CaseRobustnessResult] = []

    for case in cases:
        # 1. Base evaluation
        if stub_responses is not None:
            base_resp = stub_responses.get(case.id, "")
        elif generator is not None:
            base_resp = _generate_response(generator, [m.model_dump() for m in case.messages])
        else:
            base_resp = ""

        base_score = score_case(case, base_resp)

        # 2. Perturbation evaluation
        user_msg_idx = -1
        for i, m in enumerate(case.messages):
            if m.role == "user":
                user_msg_idx = i

        perturbed_results: dict[str, bool] = {}
        if user_msg_idx >= 0:
            orig_text = case.messages[user_msg_idx].content
            perturbed_texts = engine.generate_perturbations(orig_text)
            for ptype in ["distractor_injection", "typo_noise", "negation_constraint", "entity_swap"]:
                p_text = perturbed_texts[ptype]
                # Clone case
                p_messages = [
                    EvalMessage(role=m.role, content=p_text if j == user_msg_idx else m.content)
                    for j, m in enumerate(case.messages)
                ]
                p_case = EvalCase(
                    id=f"{case.id}_{ptype}",
                    messages=p_messages,
                    expect=case.expect,
                )
                if stub_responses is not None:
                    p_resp = stub_responses.get(f"{case.id}_{ptype}", stub_responses.get(case.id, ""))
                elif generator is not None:
                    p_resp = _generate_response(generator, [m.model_dump() for m in p_messages])
                else:
                    p_resp = ""

                p_score = score_case(p_case, p_resp)
                perturbed_results[ptype] = p_score.passed
        else:
            # Fallback if no user message found
            for ptype in ["distractor_injection", "typo_noise", "negation_constraint", "entity_swap"]:
                perturbed_results[ptype] = base_score.passed

        results.append(
            CaseRobustnessResult(
                case_id=case.id,
                base_passed=base_score.passed,
                perturbed_results=perturbed_results,
            )
        )

    return compute_robustness_report(results)
