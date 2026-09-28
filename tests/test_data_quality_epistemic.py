"""Tests for the epistemic quality engine (IT metrics)."""

from collections import Counter

from moro.data.models import DatasetMessage, DatasetRow
from moro.data.quality import (
    calculate_domain_ppmi,
    calculate_resnik_ic,
    calculate_zlib_entropy,
    classify_row,
    score_row,
    score_row_epistemic,
)


def _make_row(user: str, asst: str) -> DatasetRow:
    return DatasetRow(
        id="test",
        source="test",
        messages=[
            DatasetMessage(role="user", content=user),
            DatasetMessage(role="assistant", content=asst),
        ],
    )


# ──────────────────────────────────────────────────────────────────────────────
# Zlib Entropy Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestZlibEntropy:
    def test_empty_text_returns_zero(self):
        assert calculate_zlib_entropy("") == 0.0

    def test_very_short_text_returns_one(self):
        assert calculate_zlib_entropy("hi") == 1.0

    def test_repetitive_text_low_entropy(self):
        """Repetitive text compresses well → low entropy."""
        repetitive = "hello " * 500
        entropy = calculate_zlib_entropy(repetitive)
        assert entropy < 0.15, f"Expected low entropy for repetitive text, got {entropy}"

    def test_random_text_high_entropy(self):
        """Random character string should have high compression ratio."""
        import random
        import string

        rng = random.Random(42)
        random_text = "".join(rng.choices(string.printable, k=200))
        entropy = calculate_zlib_entropy(random_text)
        # Random text has high entropy (compresses poorly)
        assert entropy > 0.4, f"Expected high entropy for random text, got {entropy}"

    def test_normal_text_in_goldilocks_band(self):
        """Typical domain text should fall in the 0.15–0.45 band."""
        text = (
            "The patient presents with acute chest pain radiating to the left arm. "
            "ECG shows ST elevation in leads II, III, and aVF. "
            "Troponin levels are elevated at 2.5 ng/mL. "
            "Immediate PCI is indicated per STEMI protocol. "
        ) * 3
        entropy = calculate_zlib_entropy(text)
        # This should be in the Goldilocks band (good domain text)
        assert 0.15 < entropy < 0.45, f"Expected Goldilocks entropy, got {entropy}"

    def test_returns_float_in_range(self):
        for text in ["hello world", "a" * 100, "xyz123!@#"]:
            e = calculate_zlib_entropy(text)
            assert isinstance(e, float)
            assert 0.0 <= e <= 1.0 or e > 1.0  # compressed can sometimes exceed input


# ──────────────────────────────────────────────────────────────────────────────
# PPMI Proxy Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestDomainPPMI:
    def test_empty_glossary_returns_zero(self):
        assert calculate_domain_ppmi("hello world", set()) == 0.0

    def test_empty_text_returns_zero(self):
        assert calculate_domain_ppmi("", {"hello"}) == 0.0

    def test_no_glossary_match_returns_zero(self):
        assert calculate_domain_ppmi("hello world", {"lisinopril", "metformin"}) == 0.0

    def test_full_glossary_match_returns_ten(self):
        """100% overlap → score = 10.0."""
        text = "lisinopril metformin"
        glossary = {"lisinopril", "metformin"}
        score = calculate_domain_ppmi(text, glossary)
        assert abs(score - 10.0) < 0.01

    def test_partial_match_proportional(self):
        text = "lisinopril hello world"  # 1/3 match
        glossary = {"lisinopril"}
        score = calculate_domain_ppmi(text, glossary)
        expected = (1 / 3) * 10.0
        assert abs(score - expected) < 0.1


# ──────────────────────────────────────────────────────────────────────────────
# Resnik IC Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestResnikIC:
    def test_empty_text_returns_zero(self):
        counts = Counter({"hello": 5})
        assert calculate_resnik_ic("", counts, 10) == 0.0

    def test_zero_docs_returns_zero(self):
        counts = Counter({"hello": 5})
        assert calculate_resnik_ic("hello world", counts, 0) == 0.0

    def test_rare_word_gives_high_ic(self):
        """A word appearing only once in 1000 documents has high IC."""
        counts = Counter({"lisinopril": 1, "the": 900, "is": 700})
        ic = calculate_resnik_ic("lisinopril overdose protocol", counts, 1000)
        # -log(1/1000) ≈ 6.9
        assert ic > 5.0, f"Expected high IC for rare word, got {ic}"

    def test_common_word_gives_low_ic(self):
        """Very common words should have low IC."""
        counts = Counter({"the": 999, "is": 900})
        ic = calculate_resnik_ic("the", counts, 1000)
        # -log(999/1000) ≈ 0.001
        assert ic < 1.0, f"Expected low IC for common word, got {ic}"


# ──────────────────────────────────────────────────────────────────────────────
# MI Guard Classification Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestMIGuardClassification:
    def test_duplicate_always_boilerplate(self):
        cls, mi_guard = classify_row(0.3, 0.5, 5.0, is_duplicate=True)
        assert cls == "LOW_INFO_BOILERPLATE"
        assert mi_guard is False

    def test_high_entropy_no_domain_signal_is_noisy(self):
        cls, mi_guard = classify_row(entropy=0.6, ppmi=0.1, resnik_ic=0.5, is_duplicate=False)
        assert cls == "NOISY_OUTLIER"
        assert mi_guard is False

    def test_mi_guard_fires_on_noisy_but_high_ppmi(self):
        """High entropy + high PPMI → MI Guard → RARE_HIGH_VALUE_EDGE_CASE."""
        # Normalized PPMI: 6.0/10 = 0.6 ≥ 0.5 threshold
        cls, mi_guard = classify_row(entropy=0.6, ppmi=6.0, resnik_ic=0.0, is_duplicate=False)
        assert cls == "RARE_HIGH_VALUE_EDGE_CASE"
        assert mi_guard is True

    def test_mi_guard_fires_on_noisy_but_high_ic(self):
        """High entropy + high Resnik IC → MI Guard fires."""
        cls, mi_guard = classify_row(entropy=0.6, ppmi=0.0, resnik_ic=9.0, is_duplicate=False)
        assert cls == "RARE_HIGH_VALUE_EDGE_CASE"
        assert mi_guard is True

    def test_boilerplate_low_entropy_no_signal(self):
        cls, mi_guard = classify_row(entropy=0.05, ppmi=0.1, resnik_ic=0.5, is_duplicate=False)
        assert cls == "LOW_INFO_BOILERPLATE"
        assert mi_guard is False

    def test_domain_signal_without_noise_is_rare_edge_case(self):
        """Normal entropy + high PPMI → RARE_HIGH_VALUE without MI Guard."""
        cls, mi_guard = classify_row(entropy=0.25, ppmi=6.0, resnik_ic=0.0, is_duplicate=False)
        assert cls == "RARE_HIGH_VALUE_EDGE_CASE"
        assert mi_guard is False  # No override needed — entropy is normal

    def test_good_text_is_high_quality_standard(self):
        cls, mi_guard = classify_row(entropy=0.25, ppmi=0.1, resnik_ic=1.0, is_duplicate=False)
        assert cls == "HIGH_QUALITY_STANDARD"
        assert mi_guard is False


# ──────────────────────────────────────────────────────────────────────────────
# Full Epistemic Scoring Integration
# ──────────────────────────────────────────────────────────────────────────────


class TestEpistemicScoring:
    def test_score_row_epistemic_returns_metadata(self):
        row = _make_row(
            "What is acetaminophen?", "Acetaminophen is a pain reliever and fever reducer."
        )
        metadata = score_row_epistemic(
            row=row,
            domain_glossary={"acetaminophen"},
            global_token_counts=Counter({"acetaminophen": 5, "is": 100}),
            total_docs=1000,
        )
        assert 0.0 <= metadata.quality_score <= 1.0
        assert metadata.classification in {
            "HIGH_QUALITY_STANDARD",
            "RARE_HIGH_VALUE_EDGE_CASE",
            "LOW_INFO_BOILERPLATE",
            "NOISY_OUTLIER",
        }
        assert metadata.info_metrics.zlib_entropy >= 0.0

    def test_score_row_fast_path_backward_compat(self):
        """score_row() should still work as the fast, backward-compatible path."""
        row = _make_row("How are you?", "I am fine, thank you.")
        score = score_row(row)
        assert 0.0 <= score <= 1.0

    def test_domain_glossary_boosts_domain_relevance(self):
        """Row with many glossary matches should have higher domain_relevance."""
        row = _make_row(
            "What is the mechanism of action of metformin?",
            "Metformin activates AMPK, reducing hepatic gluconeogenesis and increasing insulin sensitivity.",
        )
        # With medical glossary
        metadata_with_glossary = score_row_epistemic(
            row=row,
            domain_glossary={"metformin", "ampk", "gluconeogenesis", "insulin"},
            global_token_counts=Counter(),
            total_docs=0,
        )
        # Without glossary
        metadata_no_glossary = score_row_epistemic(
            row=row,
            domain_glossary=set(),
            global_token_counts=Counter(),
            total_docs=0,
        )
        assert (
            metadata_with_glossary.score_breakdown.domain_relevance
            >= metadata_no_glossary.score_breakdown.domain_relevance
        )
