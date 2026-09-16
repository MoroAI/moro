"""
Eval runner — runs an eval suite against a model, scores each case, stores results.

For MVP, runs against an ALREADY LOADED adapter (or base model) using the HF pipeline.
Falls back to a mock/stub runner when torch is not available.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from moro.core.errors import DependencyError
from moro.eval.loader import load_suite
from moro.eval.models import CaseScore, EvalResult
from moro.eval.scorers import score_case


def _generate_response(
    model_path: str,
    messages: list[dict],
    max_new_tokens: int = 256,
) -> str:
    """
    Generate a response for a list of messages using a local model.
    Requires torch + transformers.
    """
    try:
        import torch
        from transformers import pipeline
    except ImportError as exc:
        raise DependencyError(
            "torch and transformers are required for eval.\n"
            "Install with: pip install 'moroai[train]'"
        ) from exc

    pipe = pipeline(
        "text-generation",
        model=model_path,
        device_map="auto",
        torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float32,
        max_new_tokens=max_new_tokens,
    )

    # Format messages as a simple prompt
    prompt = (
        "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in messages) + "\nAssistant:"
    )

    outputs = pipe(prompt, do_sample=False)
    text: str = outputs[0]["generated_text"]

    # Strip the prompt prefix
    if text.startswith(prompt):
        text = text[len(prompt) :].strip()

    return text


def run_suite(
    suite_path: Path,
    model_path: str,
    run_id: str | None = None,
    max_samples: int | None = None,
    stub_responses: dict[str, str] | None = None,
) -> EvalResult:
    """
    Run an eval suite against a model.

    Args:
        suite_path: Path to eval YAML file.
        model_path: HF model path or local adapter path.
        run_id: Optional run ID for linking results.
        max_samples: Limit number of cases evaluated.
        stub_responses: Dict {case_id: response} for testing without a real model.

    Returns:
        EvalResult with per-case scores.
    """
    suite = load_suite(suite_path)
    cases = suite.cases
    if max_samples:
        cases = cases[:max_samples]

    case_scores: list[CaseScore] = []

    for case in cases:
        if stub_responses is not None:
            response = stub_responses.get(case.id, "")
        else:
            messages = [m.model_dump() for m in case.messages]
            try:
                response = _generate_response(model_path, messages)
            except Exception as exc:
                case_scores.append(
                    CaseScore(
                        case_id=case.id,
                        passed=False,
                        score=0.0,
                        response="",
                        details={"error": str(exc)},
                    )
                )
                continue

        case_scores.append(score_case(case, response))

    total = len(case_scores)
    passed = sum(1 for s in case_scores if s.passed)
    pass_rate = round(passed / total, 4) if total else 0.0
    avg_score = round(sum(s.score for s in case_scores) / total, 4) if total else 0.0

    from moro.core.ids import new_id

    return EvalResult(
        id=new_id("eval"),
        suite_name=suite.name,
        run_id=run_id,
        model=model_path,
        created_at=datetime.now(timezone.utc),
        total_cases=total,
        pass_rate=pass_rate,
        avg_score=avg_score,
        metrics={"pass_rate": pass_rate, "avg_score": avg_score},
        cases=case_scores,
    )
