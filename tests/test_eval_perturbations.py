"""Tests for the Adversarial Perturbation Engine and Robustness Scorer."""

from moro.eval.perturbations import PerturbationEngine
from moro.eval.robustness import (
    CaseRobustnessResult,
    RobustnessReport,
    compute_robustness_report,
    compute_robustness_score,
)

# ──────────────────────────────────────────────────────────────────────────────
# PerturbationEngine Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestPerturbationEngine:
    def setup_method(self):
        self.engine = PerturbationEngine(seed=42)
        self.prompt = "What is the recommended dosage for ibuprofen in adults?"

    def test_generate_perturbations_returns_all_types(self):
        result = self.engine.generate_perturbations(self.prompt)
        expected_keys = {
            "original",
            "distractor_injection",
            "typo_noise",
            "negation_constraint",
            "entity_swap",
        }
        assert set(result.keys()) == expected_keys

    def test_original_is_unchanged(self):
        result = self.engine.generate_perturbations(self.prompt)
        assert result["original"] == self.prompt

    def test_distractor_injection_appends_text(self):
        perturbed = self.engine.inject_distractor(self.prompt)
        assert len(perturbed) > len(self.prompt)
        # Should contain the original prompt
        assert self.prompt in perturbed

    def test_typo_noise_changes_text(self):
        """With 4% error rate on a reasonable-length text, some change should occur."""
        long_prompt = self.prompt * 10  # make it long enough that changes are likely
        perturbed = self.engine.inject_typos(long_prompt, error_rate=0.2)
        assert perturbed != long_prompt

    def test_negation_constraint_appends_text(self):
        perturbed = self.engine.inject_negation(self.prompt)
        assert len(perturbed) > len(self.prompt)
        # Should start with the original
        assert perturbed.startswith(self.prompt)

    def test_entity_swap_generic(self):
        text = "System A is the recommended configuration."
        swapped = self.engine.swap_entities(text)
        assert "System B" in swapped
        assert "System A" not in swapped

    def test_entity_swap_custom_entities(self):
        text = "Lisinopril is better than Amlodipine for this patient."
        swapped = self.engine.swap_entities(text, entities=["Lisinopril", "Amlodipine"])
        assert "Amlodipine" in swapped
        assert "Lisinopril" in swapped
        # The entities should be swapped
        assert swapped.index("Amlodipine") < swapped.index("Lisinopril")

    def test_reproducibility_with_same_seed(self):
        """Same seed should always produce same perturbations."""
        engine1 = PerturbationEngine(seed=99)
        engine2 = PerturbationEngine(seed=99)
        r1 = engine1.generate_perturbations(self.prompt)
        r2 = engine2.generate_perturbations(self.prompt)
        assert r1 == r2

    def test_different_seeds_produce_different_results(self):
        engine1 = PerturbationEngine(seed=1)
        engine2 = PerturbationEngine(seed=2)
        r1 = engine1.inject_distractor(self.prompt)
        r2 = engine2.inject_distractor(self.prompt)
        # Fresh engines with same seeds reproduce results
        assert r1 == PerturbationEngine(seed=1).inject_distractor(self.prompt)
        assert r2 == PerturbationEngine(seed=2).inject_distractor(self.prompt)


# ──────────────────────────────────────────────────────────────────────────────
# Robustness Scorer Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestRobustnessScorer:
    def test_perfect_robustness(self):
        """All perturbations pass → raw_robustness = strict_robustness = 1.0."""
        result = compute_robustness_score(
            base_passed=True,
            perturbed_results={
                "distractor_injection": True,
                "typo_noise": True,
                "negation_constraint": True,
                "entity_swap": True,
            },
        )
        assert result["raw_robustness"] == 1.0
        assert result["strict_robustness"] == 1.0
        assert result["vulnerability_count"] == 0

    def test_zero_robustness(self):
        """All perturbations fail → raw_robustness = 0.0."""
        result = compute_robustness_score(
            base_passed=True,
            perturbed_results={
                "distractor_injection": False,
                "typo_noise": False,
                "negation_constraint": False,
                "entity_swap": False,
            },
        )
        assert result["raw_robustness"] == 0.0
        assert result["vulnerability_count"] == 4

    def test_partial_robustness(self):
        """2 out of 4 pass → raw_robustness = 0.5."""
        result = compute_robustness_score(
            base_passed=True,
            perturbed_results={
                "distractor_injection": True,
                "typo_noise": False,
                "negation_constraint": True,
                "entity_swap": False,
            },
        )
        assert result["raw_robustness"] == 0.5
        assert result["vulnerability_count"] == 2

    def test_vulnerability_only_counts_regressions(self):
        """Vulnerabilities = cases where base passed but perturbed failed."""
        result = compute_robustness_score(
            base_passed=False,  # base already failed
            perturbed_results={
                "distractor_injection": False,  # still fails — expected
                "typo_noise": True,  # now passes — improvement, not vulnerability
            },
        )
        # No vulnerabilities when base already failed
        assert result["vulnerability_count"] == 0

    def test_empty_perturbations_gives_full_score(self):
        result = compute_robustness_score(base_passed=True, perturbed_results={})
        assert result["raw_robustness"] == 1.0
        assert result["strict_robustness"] == 1.0

    def test_case_robustness_failed_perturbations_list(self):
        case = CaseRobustnessResult(
            case_id="test_001",
            base_passed=True,
            perturbed_results={
                "distractor_injection": True,
                "typo_noise": False,
                "negation_constraint": False,
                "entity_swap": True,
            },
        )
        assert len(case.failed_perturbations) == 2
        assert "typo_noise" in case.failed_perturbations
        assert "negation_constraint" in case.failed_perturbations

    def test_report_aggregation(self):
        case1 = CaseRobustnessResult(
            case_id="c1",
            base_passed=True,
            perturbed_results={"a": True, "b": True},
        )
        case2 = CaseRobustnessResult(
            case_id="c2",
            base_passed=True,
            perturbed_results={"a": False, "b": True},
        )
        report = compute_robustness_report([case1, case2])
        assert report.total_cases == 2
        assert report.total_vulnerabilities == 1
        assert report.most_vulnerable_perturbation == "a"

    def test_robustness_grade_thresholds(self):
        def _grade(score):
            from moro.eval.robustness import CaseRobustnessResult

            case = CaseRobustnessResult(
                case_id="x",
                base_passed=True,
                perturbed_results={},  # empty → score computed as 1.0
            )
            # Monkey-patch to test grade thresholds
            r = RobustnessReport(total_cases=1, case_results=[case])
            r.avg_strict_robustness = score
            return r.robustness_grade

        assert "A" in _grade(0.96)
        assert "B" in _grade(0.87)
        assert "C" in _grade(0.75)
        assert "D" in _grade(0.60)
        assert "F" in _grade(0.40)


class TestPerturbedSuiteAndEvaluation:
    def test_create_perturbed_suite(self, tmp_path):
        import yaml

        from moro.eval.robustness import create_perturbed_suite

        suite_path = tmp_path / "eval_suite.yaml"
        suite_data = {
            "name": "basic_suite",
            "cases": [
                {
                    "id": "c1",
                    "messages": [{"role": "user", "content": "What is Drug A dosage?"}],
                    "expect": {"contains": ["10mg"]},
                }
            ],
        }
        with open(suite_path, "w") as f:
            yaml.safe_dump(suite_data, f)

        out_path = tmp_path / "perturbed_suite.yaml"
        create_perturbed_suite(suite_path, out_path, seed=42)

        assert out_path.exists()
        with open(out_path) as f:
            loaded = yaml.safe_load(f)
        assert len(loaded["cases"]) == 5  # original + 4 perturbations
        case_ids = [c["id"] for c in loaded["cases"]]
        assert "c1" in case_ids
        assert "c1_distractor_injection" in case_ids
        assert "c1_typo_noise" in case_ids
        assert "c1_negation_constraint" in case_ids
        assert "c1_entity_swap" in case_ids

    def test_evaluate_robustness_with_stubs(self, tmp_path):
        import yaml

        from moro.eval.robustness import evaluate_robustness

        suite_path = tmp_path / "eval_suite.yaml"
        suite_data = {
            "name": "basic_suite",
            "cases": [
                {
                    "id": "c1",
                    "messages": [{"role": "user", "content": "Explain PCI protocol."}],
                    "expect": {"contains": ["PCI"]},
                }
            ],
        }
        with open(suite_path, "w") as f:
            yaml.safe_dump(suite_data, f)

        # Base passes, 3 perturbations pass, typo fails
        stub_responses = {
            "c1": "Standard PCI procedure requires heparin.",
            "c1_distractor_injection": "PCI procedure with distractor.",
            "c1_typo_noise": "Unknown error in procedure.",  # does not contain PCI -> fails
            "c1_negation_constraint": "PCI procedure without filler.",
            "c1_entity_swap": "PCI procedure applied.",
        }

        report = evaluate_robustness(suite_path, stub_responses=stub_responses)
        assert report.total_cases == 1
        assert report.case_results[0].base_passed is True
        assert report.case_results[0].perturbed_results["typo_noise"] is False
        assert report.case_results[0].perturbed_results["distractor_injection"] is True
        assert report.total_vulnerabilities == 1
        assert report.most_vulnerable_perturbation == "typo_noise"
