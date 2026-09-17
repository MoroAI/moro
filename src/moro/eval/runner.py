"""Evaluate a model or adapter using one explicitly loaded local pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from moro.core.errors import DependencyError, EvalError
from moro.core.hashing import sha256_directory, sha256_file
from moro.eval.loader import load_suite
from moro.eval.models import CaseScore, EvalResult
from moro.eval.scorers import score_case


def _load_generator(model_path: str, *, local_only: bool, revision: str | None = None):
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
    except ImportError as exc:
        raise DependencyError("Install moroai[train] for model-backed evaluation.") from exc
    from moro.models.loading import model_load_options, resolve_model_reference

    reference = resolve_model_reference(model_path, local_only=local_only, revision=revision)
    options = model_load_options(local_only=local_only)
    # Resolve remote IDs explicitly as well so adapter detection uses the selected revision.
    if not Path(reference).is_dir():
        from huggingface_hub import snapshot_download

        reference = snapshot_download(reference, revision=revision)
    adapter_config = Path(reference) / "adapter_config.json"
    if adapter_config.exists():
        from peft import PeftConfig, PeftModel

        adapter = PeftConfig.from_pretrained(reference, local_files_only=local_only)
        base_reference = resolve_model_reference(
            adapter.base_model_name_or_path, local_only=local_only, revision=adapter.revision
        )
        model = AutoModelForCausalLM.from_pretrained(
            base_reference, revision=adapter.revision, **options
        )
        model = PeftModel.from_pretrained(model, reference, local_files_only=local_only)
    else:
        model = AutoModelForCausalLM.from_pretrained(reference, **options)
    tokenizer = AutoTokenizer.from_pretrained(reference, **options)
    if not tokenizer.chat_template:
        raise EvalError("Evaluation requires a tokenizer chat template.")
    return pipeline("text-generation", model=model, tokenizer=tokenizer, device_map="auto")


def _generate_response(generator, messages: list[dict], max_new_tokens: int = 256) -> str:
    outputs = generator(messages, do_sample=False, max_new_tokens=max_new_tokens)
    generated = outputs[0]["generated_text"]
    if not isinstance(generated, list) or not generated or generated[-1]["role"] != "assistant":
        raise EvalError("Model generation did not return an assistant message.")
    return generated[-1]["content"]


def run_suite(
    suite_path: Path,
    model_path: str,
    run_id: str | None = None,
    max_samples: int | None = None,
    stub_responses: dict[str, str] | None = None,
    local_only: bool = True,
    revision: str | None = None,
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
    if max_samples is not None and max_samples < 1:
        raise EvalError("max_samples must be positive.")
    suite_hash = sha256_file(suite_path)
    suite = load_suite(suite_path)
    adapter_hash = sha256_directory(Path(model_path)) if run_id else None
    cases = suite.cases
    if max_samples:
        cases = cases[:max_samples]

    if not cases:
        raise EvalError("Evaluation suite has no cases.")
    generator = None
    if stub_responses is None:
        generator = _load_generator(model_path, local_only=local_only, revision=revision)
    case_scores: list[CaseScore] = []

    for case in cases:
        if stub_responses is not None:
            response = stub_responses.get(case.id, "")
        else:
            messages = [m.model_dump() for m in case.messages]
            try:
                response = _generate_response(generator, messages)
            except Exception as exc:
                raise EvalError(
                    f"Generation failed for case {case.id}; no quality result saved."
                ) from exc

        case_scores.append(score_case(case, response))

    total = len(case_scores)
    passed = sum(1 for s in case_scores if s.passed)
    pass_rate = round(passed / total, 4) if total else 0.0
    avg_score = round(sum(s.score for s in case_scores) / total, 4) if total else 0.0

    from moro.core.ids import new_id

    if sha256_file(suite_path) != suite_hash:
        raise EvalError("Evaluation suite changed during execution; rerun evaluation.")
    if run_id and sha256_directory(Path(model_path)) != adapter_hash:
        raise EvalError("Adapter changed during execution; rerun evaluation.")
    scored = [bool(c.expect and c.expect.model_dump(exclude_defaults=True)) for c in cases]
    safety = [
        s.passed and valid for c, s, valid in zip(cases, case_scores, scored) if "safety" in c.tags
    ]
    return EvalResult(
        id=new_id("eval"),
        suite_name=suite.name,
        run_id=run_id,
        model=model_path,
        created_at=datetime.now(timezone.utc),
        total_cases=total,
        pass_rate=pass_rate,
        avg_score=avg_score,
        suite_sha256=suite_hash,
        adapter_sha256=adapter_hash,
        execution_kind="stub" if stub_responses is not None else "model",
        fully_scored=all(scored),
        safety_pass=all(safety) if safety else None,
        metrics={"pass_rate": pass_rate, "avg_score": avg_score},
        cases=case_scores,
    )
