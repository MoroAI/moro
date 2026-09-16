from pathlib import Path

import yaml
from pydantic import ValidationError

from moro.core.errors import EvalError
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

    return suite
