import csv
import json
from pathlib import Path

from moro.core.errors import DatasetError

SUPPORTED_EXTENSIONS = {".jsonl", ".json", ".csv", ".txt", ".md", ".markdown"}


def detect_format(path: Path, requested: str = "auto") -> str:
    if requested != "auto":
        return requested
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".json"}:
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    if suffix == ".txt":
        return "txt"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return "auto"


def read_raw_rows(path: Path, format: str = "auto", limit: int | None = None) -> list[dict]:
    """
    Read a dataset file and return a list of raw row dicts.
    Each row is augmented with _source_file, _line_number, _format metadata keys.
    """
    path = Path(path)
    if limit is not None and limit < 1:
        raise DatasetError("limit must be positive")

    if not path.exists():
        raise DatasetError(f"Dataset source does not exist: {path}")

    if path.is_dir():
        # Directory mode: read all supported files recursively
        rows: list[dict] = []
        found = list(path.rglob("*"))
        files = [f for f in found if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS]
        if not files:
            raise DatasetError(f"No supported dataset files found in directory: {path}")
        for f in sorted(files):
            rows.extend(read_raw_rows(f, format, None if limit is None else limit - len(rows)))
            if limit is not None and len(rows) >= limit:
                break
        return rows

    fmt = detect_format(path, format)

    if fmt in {"jsonl", "json"}:
        return _read_jsonl(path, limit)
    if fmt == "csv":
        return _read_csv(path, limit)
    if fmt in {"txt", "markdown", "auto"}:
        return _read_text(path, limit)

    raise DatasetError(f"Unsupported dataset format for file: {path}")


def _tag(obj: dict, path: Path, line_number: int, fmt: str) -> dict:
    obj = dict(obj)
    obj["_source_file"] = str(path)
    obj["_line_number"] = line_number
    obj["_format"] = fmt
    return obj


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []

    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Invalid JSON in file: {path}") from exc
        if isinstance(data, list):
            selected = data if limit is None else data[:limit]
            if any(not isinstance(item, dict) for item in selected):
                raise DatasetError(f"JSON array must contain objects: {path}")
            return [_tag(item, path, i + 1, "json") for i, item in enumerate(selected)]
        if isinstance(data, dict):
            return [_tag(data, path, 1, "json")]
        raise DatasetError(f"Unsupported JSON structure in: {path}")

    with path.open("r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DatasetError(f"Invalid JSONL at {path}:{ln}") from exc
            if not isinstance(obj, dict):
                raise DatasetError(f"JSONL row must be an object at {path}:{ln}")
            rows.append(_tag(obj, path, ln, "jsonl"))
            if limit is not None and len(rows) >= limit:
                break

    return rows


def _read_csv(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for ln, row in enumerate(reader, start=2):
            rows.append(_tag(dict(row), path, ln, "csv"))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _read_text(path: Path, limit: int | None = None) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            text = line.strip()
            if not text:
                continue
            rows.append(_tag({"text": text}, path, ln, "text"))
            if limit is not None and len(rows) >= limit:
                break
    return rows
