"""
Tests for DeterministicPreferenceExtractor.
"""

from moro.flywheel.extractors.deterministic_extractor import DeterministicPreferenceExtractor
from moro.flywheel.models import FeedbackType, InferenceLogPayload


def test_extract_human_correction():
    extractor = DeterministicPreferenceExtractor()
    log = InferenceLogPayload(
        session_id="s1",
        prompt="What is the dosage of Drug X?",
        completion="Drug X dosage is 500mg daily.",
        human_correction="Drug X dosage is 250mg twice daily with meals.",
        user_rating=-0.5,
    )
    pairs = extractor.extract_pairs([log])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.feedback_type == FeedbackType.EXPLICIT_HUMAN_CORRECTION
    assert pair.chosen == "Drug X dosage is 250mg twice daily with meals."
    assert pair.rejected == "Drug X dosage is 500mg daily."
    assert pair.confidence_delta > 0


def test_extract_negative_rating_with_context():
    extractor = DeterministicPreferenceExtractor()
    log = InferenceLogPayload(
        session_id="s2",
        prompt="What protocol applies to PCI?",
        completion="Protocol Alpha applies to all procedures.",
        context="The STEMI PCI Clinical Guidelines dictate immediate heparin administration.",
        user_rating=-0.8,
    )
    pairs = extractor.extract_pairs([log])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.feedback_type == FeedbackType.IMPLICIT_NEGATIVE_RATING
    assert "STEMI PCI Clinical Guidelines" in pair.chosen
    assert pair.rejected == "Protocol Alpha applies to all procedures."


def test_extract_positive_reinforcement():
    extractor = DeterministicPreferenceExtractor()
    log = InferenceLogPayload(
        session_id="s3",
        prompt="Explain hypertension pathophysiology.",
        completion="Hypertension results from increased systemic vascular resistance and cardiac output. Renin-angiotensin-aldosterone system plays a major role.",
        user_rating=1.0,
    )
    pairs = extractor.extract_pairs([log])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.feedback_type == FeedbackType.POSITIVE_REINFORCEMENT
    assert pair.chosen == log.completion
    assert len(pair.rejected) < len(pair.chosen)


def test_extract_automated_rule_violation():
    extractor = DeterministicPreferenceExtractor()
    log = InferenceLogPayload(
        session_id="s4",
        prompt="Summarize Section 4.",
        completion="Section 4 contains legal clauses.",
        context="Section 4 details mandatory arbitration and governing law in Delaware.",
        metadata={"rule_violation": "too_generic"},
    )
    pairs = extractor.extract_pairs([log])
    assert len(pairs) == 1
    assert pairs[0].feedback_type == FeedbackType.AUTOMATED_RULE_VIOLATION
