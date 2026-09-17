import hashlib
import json
from pathlib import Path


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
