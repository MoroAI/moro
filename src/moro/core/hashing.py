import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter


def sha256_file(path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    path = Path(path)

    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)

    return hasher.hexdigest()


def sha256_text(text: str) -> str:
    """Compute SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot_fields(raw: str) -> dict:
    def unique_fields(pairs):
        fields = {}
        for key, value in pairs:
            if key in fields:
                raise ValueError(f"Duplicate snapshot field: {key}")
            fields[key] = value
        return fields

    def reject_constant(value):
        raise ValueError(f"Non-finite snapshot value: {value}")

    fields = json.loads(raw, object_pairs_hook=unique_fields, parse_constant=reject_constant)
    if not isinstance(fields, dict):
        raise ValueError("Configuration snapshot must be an object.")
    # Also rejects overflowing numeric literals such as 1e999.
    json.dumps(fields, allow_nan=False)
    return fields


def config_snapshot_hash(raw: str) -> str:
    """Versioned hash of saved fields, independent of whitespace and key order."""
    canonical = json.dumps(
        _snapshot_fields(raw),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "config-json-v1:" + sha256_text(canonical)


def matches_config_snapshot(raw: str, recorded: str) -> bool:
    """Check v1 or legacy hashes without injecting new configuration defaults."""
    if recorded.startswith("config-json-v1:"):
        return config_snapshot_hash(raw) == recorded
    if ":" in recorded:
        return False
    fields = _snapshot_fields(raw)
    # Legacy training used Pydantic's float formatting. Early export tooling
    # also used stdlib JSON; recognize either historical encoding explicitly.
    pydantic_json = TypeAdapter(dict[str, Any]).dump_json(fields).decode("utf-8")
    stdlib_json = json.dumps(fields, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return recorded in {sha256_text(pydantic_json), sha256_text(stdlib_json)}


def sha256_directory(directory: Path) -> str:
    """Bind every regular file's relative name and contents; reject links."""
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Fingerprint requires a materialized directory.")
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Cannot fingerprint symbolic link: {path}")
        if path.is_file():
            entries.append([path.relative_to(directory).as_posix(), sha256_file(path)])
    return sha256_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")))
