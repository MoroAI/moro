"""
MoroAI Deterministic Preference Extractor.

Transforms production inference logs into DPO preference pairs using deterministic rules.
No external LLM calls required — runs CPU-native and locally.
"""

from __future__ import annotations

import uuid

from moro.flywheel.architecture import AbstractPreferenceExtractor, AbstractSyntheticGenerator
from moro.flywheel.generators.grounded_generator import DeterministicGroundedGenerator
from moro.flywheel.models import FeedbackType, InferenceLogPayload, PreferencePair


class DeterministicPreferenceExtractor(AbstractPreferenceExtractor):
    """
    Extracts DPO preference pairs from production logs using 4 distinct signal types.
    """

    def __init__(
        self,
        synthetic_generator: AbstractSyntheticGenerator | None = None,
        min_confidence_delta: float = 0.05,
    ):
        self.synthetic_generator = synthetic_generator or DeterministicGroundedGenerator()
        self.min_confidence_delta = min_confidence_delta

    def extract_pairs(self, logs: list[InferenceLogPayload]) -> list[PreferencePair]:
        """Transform raw inference logs into DPO preference pairs."""
        pairs: list[PreferencePair] = []
        for log in logs:
            extracted = self._extract_single(log)
            if extracted:
                pairs.extend(extracted)
        return pairs

    def _extract_single(self, log: InferenceLogPayload) -> list[PreferencePair]:
        pairs: list[PreferencePair] = []

        # Rule 1: Explicit Human Correction (Highest quality signal)
        if log.human_correction and log.human_correction.strip():
            pair = self._extract_human_correction(log)
            if pair:
                pairs.append(pair)
            return pairs

        # Rule 2: Implicit Negative Rating
        if log.user_rating is not None and log.user_rating < 0:
            pair = self._extract_negative_rating(log)
            if pair:
                pairs.append(pair)
            return pairs

        # Rule 3: Automated Rule Violation
        if log.metadata.get("rule_violation") or log.metadata.get("flagged"):
            pair = self._extract_rule_violation(log)
            if pair:
                pairs.append(pair)
            return pairs

        # Rule 4: Positive Reinforcement
        if log.user_rating is not None and log.user_rating > 0.5:
            pair = self._extract_positive_reinforcement(log)
            if pair:
                pairs.append(pair)
            return pairs

        return pairs

    def _extract_human_correction(self, log: InferenceLogPayload) -> PreferencePair | None:
        if not log.human_correction or not log.human_correction.strip():
            return None

        if log.human_correction.strip() == log.completion.strip():
            return None

        confidence_delta = self._calculate_correction_confidence(
            log.completion, log.human_correction
        )
        if confidence_delta < self.min_confidence_delta:
            confidence_delta = self.min_confidence_delta

        return PreferencePair(
            pair_id=str(uuid.uuid4()),
            prompt=log.prompt,
            chosen=log.human_correction.strip(),
            rejected=log.completion.strip(),
            feedback_type=FeedbackType.EXPLICIT_HUMAN_CORRECTION,
            confidence_delta=round(confidence_delta, 3),
            source_log_id=log.metadata.get("log_id") or log.session_id,
            metadata={
                "original_latency_ms": log.latency_ms,
                "had_context": bool(log.context),
                "user_rating": log.user_rating,
            },
        )

    def _extract_negative_rating(self, log: InferenceLogPayload) -> PreferencePair | None:
        chosen = self.synthetic_generator.generate_grounded_chosen(log.prompt, log.context)
        if not chosen or chosen.strip() == log.completion.strip():
            return None

        confidence_delta = abs(log.user_rating) if log.user_rating is not None else 0.5
        return PreferencePair(
            pair_id=str(uuid.uuid4()),
            prompt=log.prompt,
            chosen=chosen.strip(),
            rejected=log.completion.strip(),
            feedback_type=FeedbackType.IMPLICIT_NEGATIVE_RATING,
            confidence_delta=round(min(1.0, max(0.1, confidence_delta)), 3),
            source_log_id=log.metadata.get("log_id") or log.session_id,
            metadata={
                "user_rating": log.user_rating,
                "generation_method": type(self.synthetic_generator).__name__,
            },
        )

    def _extract_rule_violation(self, log: InferenceLogPayload) -> PreferencePair | None:
        chosen = self.synthetic_generator.generate_grounded_chosen(log.prompt, log.context)
        if not chosen or chosen.strip() == log.completion.strip():
            return None

        return PreferencePair(
            pair_id=str(uuid.uuid4()),
            prompt=log.prompt,
            chosen=chosen.strip(),
            rejected=log.completion.strip(),
            feedback_type=FeedbackType.AUTOMATED_RULE_VIOLATION,
            confidence_delta=0.8,
            source_log_id=log.metadata.get("log_id") or log.session_id,
            metadata={"violation": log.metadata.get("rule_violation", "general_flag")},
        )

    def _extract_positive_reinforcement(self, log: InferenceLogPayload) -> PreferencePair | None:
        rejected = self._create_degraded_version(log.completion)
        if not rejected or rejected.strip() == log.completion.strip():
            return None

        confidence_delta = log.user_rating if log.user_rating is not None else 0.5
        return PreferencePair(
            pair_id=str(uuid.uuid4()),
            prompt=log.prompt,
            chosen=log.completion.strip(),
            rejected=rejected.strip(),
            feedback_type=FeedbackType.POSITIVE_REINFORCEMENT,
            confidence_delta=round(min(1.0, max(0.1, confidence_delta)), 3),
            source_log_id=log.metadata.get("log_id") or log.session_id,
            metadata={"user_rating": log.user_rating},
        )

    def _calculate_correction_confidence(self, original: str, correction: str) -> float:
        orig_words = set(original.lower().split())
        corr_words = set(correction.lower().split())
        if not orig_words or not corr_words:
            return 0.5
        union = orig_words | corr_words
        inter = orig_words & corr_words
        jaccard_distance = 1.0 - (len(inter) / len(union))
        return min(1.0, max(0.0, jaccard_distance))

    def _create_degraded_version(self, completion: str) -> str | None:
        if not completion:
            return None
        sentences = [s.strip() for s in completion.split(".") if s.strip()]
        if len(sentences) > 1:
            return ". ".join(sentences[:-1]) + "."
        else:
            cutoff = max(10, int(len(completion) * 0.6))
            return completion[:cutoff] + "..."
