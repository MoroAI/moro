"""
MoroAI Adversarial Perturbation Engine.

Generates deterministic algorithmic variations of evaluation prompts to test
model robustness against real-world noise, distractors, and entity swaps.

No external LLM calls required — all perturbations are CPU-native and
mathematically reproducible given the same seed.

Standard benchmarks test models on pristine inputs. Production users make typos,
inject distracting context, ask negatively-phrased questions, and swap entities.
A model that scores 100% on pristine inputs but collapses under noise is not
production-ready.

Perturbation Types:
  1. distractor_injection: Appends domain-sounding but irrelevant sentences
  2. typo_noise: Introduces character-level errors (swap, drop, duplicate)
  3. negation_constraint: Adds a negative instruction constraint
  4. entity_swap: Swaps key named entities to test contrastive understanding
"""

from __future__ import annotations

import random
import re

# Domain-sounding but irrelevant distractor sentences
# These sound plausible in medical/legal/regulatory contexts but add no information
DISTRACTORS = [
    "Furthermore, the regulatory compliance framework mandates quarterly audits of the archival systems.",
    "Note that the secondary endpoint metrics were evaluated using a double-blind crossover methodology.",
    "Historical data suggests that legacy API integrations may require additional latency buffers.",
    "Please ensure that all environmental impact assessments are filed according to subsection 4.2.",
    "The theoretical maximum throughput is bounded by the PCIe Gen4 bandwidth limitations.",
    "Prior authorization requirements vary by jurisdiction and are subject to annual review.",
    "The informed consent process must be documented in the patient's medical record within 24 hours.",
    "Compliance with ICH E6(R2) guidelines is mandatory for all clinical trial sponsors.",
]

# Negation constraints that test instruction-following strictness
NEGATION_CONSTRAINTS = [
    " Do not include any introductory filler or preamble.",
    " Exclude any references to legacy systems or deprecated protocols.",
    " Do not mention alternative vendors, products, or competing standards.",
    " Omit any information not directly relevant to the regulatory question.",
    " Do not speculate beyond the evidence provided in the context.",
]


class PerturbationEngine:
    """
    Generates deterministic, reproducible adversarial perturbations for eval cases.

    The engine is seeded for reproducibility — the same seed produces the same
    perturbations every time, enabling consistent regression testing.
    """

    def __init__(self, seed: int = 42):
        """
        Args:
            seed: Random seed for reproducible perturbations.
        """
        self.rng = random.Random(seed)

    def inject_distractor(self, text: str, n: int = 1) -> str:
        """
        Append 1–2 irrelevant but domain-sounding sentences.

        Tests whether the model ignores noise and still answers the core question.
        A model that fails distractor tests is pattern-matching keywords, not reasoning.
        """
        num = max(1, min(n, 2))
        selected = self.rng.sample(DISTRACTORS, min(num, len(DISTRACTORS)))
        return text + " " + " ".join(selected)

    def inject_typos(self, text: str, error_rate: float = 0.04) -> str:
        """
        Introduce realistic character-level noise (swaps, drops, duplicates).

        Error rate of 4% simulates realistic keyboard typos in professional settings.
        A robust model should still parse and answer correctly at this noise level.
        """
        chars = list(text)
        for i in range(len(chars) - 1):
            if self.rng.random() < error_rate:
                action = self.rng.choice(["swap", "drop", "dupe"])
                if action == "swap":
                    chars[i], chars[i + 1] = chars[i + 1], chars[i]
                elif action == "drop":
                    chars[i] = ""
                elif action == "dupe":
                    chars[i] = chars[i] + chars[i]
        return "".join(chars)

    def inject_negation(self, text: str) -> str:
        """
        Add a negative instruction constraint to the prompt.

        Tests instruction-following strictness. A model that cannot respect
        negative constraints is not safe in high-stakes domain applications.
        """
        constraint = self.rng.choice(NEGATION_CONSTRAINTS)
        return text + constraint

    def swap_entities(
        self,
        text: str,
        entities: list[str] | None = None,
    ) -> str:
        """
        Swap key named entities to test contrastive understanding.

        If the model just pattern-matches without understanding, it will give the
        same answer whether "Drug A" or "Drug B" is mentioned — which is wrong.

        A model that correctly adapts its answer to the swapped entity demonstrates
        genuine domain understanding rather than surface-level keyword matching.

        Args:
            text: Original prompt text.
            entities: Optional list of entities to swap. If None, applies generic swaps
                      for common placeholder patterns (System A/B, Drug A/B, etc.).
        """
        if not entities or len(entities) < 2:
            # Generic placeholder swaps for common patterns
            swaps = [
                (r"\bSystem A\b", "System B"),
                (r"\bDrug A\b", "Drug B"),
                (r"\bProtocol X\b", "Protocol Y"),
                (r"\bCompound A\b", "Compound B"),
                (r"\bProduct X\b", "Product Y"),
            ]
            result = text
            for pattern, replacement in swaps:
                if re.search(pattern, result, flags=re.IGNORECASE):
                    result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
                    break  # Only apply the first matching swap
            return result

        # Swap first two provided entities using a temp placeholder
        e1, e2 = entities[0], entities[1]
        _TEMP = "___MORO_SWAP_PLACEHOLDER___"
        text = text.replace(e1, _TEMP).replace(e2, e1).replace(_TEMP, e2)
        return text

    def generate_perturbations(
        self,
        original_prompt: str,
        entities: list[str] | None = None,
    ) -> dict[str, str]:
        """
        Generate the full suite of 4 perturbations for a single eval case.

        Args:
            original_prompt: The original, unmodified prompt.
            entities: Optional entity pair for entity swap perturbation.

        Returns:
            Dict mapping perturbation type → perturbed prompt.
            Always includes "original" for reference.
        """
        return {
            "original": original_prompt,
            "distractor_injection": self.inject_distractor(original_prompt),
            "typo_noise": self.inject_typos(original_prompt),
            "negation_constraint": self.inject_negation(original_prompt),
            "entity_swap": self.swap_entities(original_prompt, entities),
        }
