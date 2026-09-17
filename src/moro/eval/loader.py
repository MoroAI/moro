import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from moro.core.errors import DependencyError, EvalError
from moro.eval.models import EvalSuite


def load_suite(path: Path) -> EvalSuite:
    """
    Load an eval suite from a YAML file.

    Raises:
        EvalError: if the file is missing, has bad YAML, or fails schema validation.
    """
    path = Path(path).expanduser().resolve()

    if not path.exists():
        raise EvalError(f"Eval suite file not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalError(f"Could not read eval suite: {path}") from exc

    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise EvalError(f"Invalid YAML in eval suite: {path}\n{exc}") from exc

    if not isinstance(data, dict):
        raise EvalError(f"Eval suite YAML must be a mapping: {path}")

    try:
        suite = EvalSuite.model_validate(data)
    except ValidationError as exc:
        raise EvalError(f"Invalid eval suite schema ({path}):\n{exc}") from exc

    # Validate unique case IDs
    case_ids = [c.id for c in suite.cases]
    seen: set[str] = set()
    for cid in case_ids:
        if cid in seen:
            raise EvalError(f"Duplicate case ID in eval suite: {cid!r}")
        seen.add(cid)

    for case in suite.cases:
        if (
            not case.id.strip()
            or not case.messages
            or any(not m.content.strip() for m in case.messages)
        ):
            raise EvalError("Evaluation cases require an ID and nonempty messages.")
        expect = case.expect
        if expect is None:
            continue
        if not (
            expect.contains
            or expect.any_of_contains
            or expect.regex
            or expect.json_schema is not None
        ):
            raise EvalError(f"Empty expectation in case {case.id}.")
        if any(
            not term.strip() for term in expect.contains + expect.any_of_contains + expect.regex
        ):
            raise EvalError(f"Empty check in case {case.id}.")
        for pattern in expect.regex:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise EvalError(f"Invalid regex in case {case.id}: {exc}") from exc
        if expect.json_schema is not None:
            try:
                import jsonschema
            except ImportError as exc:
                raise DependencyError("JSON schema scoring requires moroai[eval].") from exc
            try:
                jsonschema.validators.validator_for(expect.json_schema).check_schema(
                    expect.json_schema
                )
            except jsonschema.SchemaError as exc:
                raise EvalError(f"Invalid JSON schema in case {case.id}: {exc}") from exc

    return suite
