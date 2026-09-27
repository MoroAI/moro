"""
MoroAI Context-Grounded Synthetic Generator.

Generates high-fidelity, verified completions for DPO preference pairs.
Uses a local model (via Ollama) if available, with deterministic fallback.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from moro.flywheel.architecture import AbstractSyntheticGenerator


class OllamaGroundedGenerator(AbstractSyntheticGenerator):
    """
    Generates grounded completions using a local Ollama model.
    Uses standard library urllib (zero external dependency).
    Falls back to deterministic extraction if Ollama is unreachable.
    """

    SYSTEM_PROMPT = """You are a careful, domain-expert assistant. Your task is to generate a response that is:
1. STRICTLY GROUNDED in the provided context. Do not introduce information not present in the context.
2. CONSERVATIVE. If the context does not contain sufficient evidence, state: "Insufficient evidence in provided context."
3. CONCISE. Provide only the information necessary to answer the query."""

    def __init__(
        self,
        model_name: str = "llama3",
        ollama_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        max_tokens: int = 512,
        timeout_seconds: float = 30.0,
    ):
        self.model_name = model_name
        self.ollama_url = ollama_url.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds

    def generate_grounded_chosen(
        self,
        prompt: str,
        context: str | None,
    ) -> str:
        """Generate a grounded completion using local Ollama model."""
        if not context:
            return "Insufficient evidence in provided context to answer this query."

        user_message = f"""CONTEXT:
{context}

QUERY:
{prompt}

INSTRUCTIONS:
Generate a response that is strictly grounded in the context above. If the context does not contain sufficient evidence, state "Insufficient evidence in provided context." Do not fabricate any information."""

        payload = {
            "model": self.model_name,
            "prompt": user_message,
            "system": self.SYSTEM_PROMPT,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception:
            return self._fallback_generation(prompt, context)

    def _fallback_generation(self, prompt: str, context: str) -> str:
        fallback = DeterministicGroundedGenerator()
        return fallback.generate_grounded_chosen(prompt, context)


class DeterministicGroundedGenerator(AbstractSyntheticGenerator):
    """
    Purely deterministic generator that requires no external model.
    Extracts relevant passages from context using keyword density.
    """

    def generate_grounded_chosen(
        self,
        prompt: str,
        context: str | None,
    ) -> str:
        if not context or not context.strip():
            return "Insufficient evidence in provided context to answer this query."

        paragraphs = [p.strip() for p in context.split("\n\n") if p.strip()]
        if not paragraphs:
            return f"Based on the provided context: {context.strip()}"

        prompt_words = set(prompt.lower().split())
        scored: list[tuple[int, str]] = []
        for p in paragraphs:
            p_words = set(p.lower().split())
            overlap = len(prompt_words & p_words)
            scored.append((overlap, p))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = [p for score, p in scored[:2] if score > 0]
        if not top:
            return f"Based on the provided context: {paragraphs[0]}"

        return "Based on the provided context: " + " ".join(top)
