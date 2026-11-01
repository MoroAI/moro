"""Bounded uploads with descriptor-relative, exclusive publication.

The project root and local filesystem administrators are trusted. Opening each
child directory relative to its parent prevents symlink substitution from
redirecting writes. Payload publication never replaces an existing object.
"""

import csv
import errno
import hashlib
import io
import json
import os
import re
import stat
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
EXTENSIONS = {".jsonl", ".json", ".csv", ".txt"}
_GENERATED_NAME = re.compile(r"[0-9a-f]{32}\.(?:jsonl|json|csv|txt)\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@contextmanager
def _raw_descriptor(root: Path):
    """Open every untrusted child with no-follow semantics, retaining the handle."""
    base = root.resolve()
    descriptor = os.open(base, _DIRECTORY_FLAGS)
    try:
        for part in ("data", "raw"):
            try:
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            try:
                child = os.open(part, _DIRECTORY_FLAGS, dir_fd=descriptor)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise HTTPException(
                        400, "Dataset directories must be real directories"
                    ) from exc
                raise
            os.close(descriptor)
            descriptor = child
        yield base / "data" / "raw", descriptor
    except (NotADirectoryError, FileNotFoundError) as exc:
        raise HTTPException(400, "Dataset directories must be real directories") from exc
    finally:
        os.close(descriptor)


def raw_directory(root: Path) -> Path:
    with _raw_descriptor(root) as (directory, _):
        return directory


def sanitize_display_name(value: str) -> str:
    """Metadata only: strip controls, path separators and excessive length."""
    value = "".join(c for c in value if not unicodedata.category(c).startswith("C"))
    return " ".join(value.replace("/", "_").replace("\\", "_").split())[:120] or "upload"


def _reject_constant(value: str):
    raise ValueError("Non-finite JSON number")


def _validate_content(text: str, suffix: str) -> int:
    if not text.strip() or any(ord(c) < 32 and c not in "\t\r\n" for c in text):
        raise ValueError("Empty or binary content")
    if suffix == ".json":
        value = json.loads(text, parse_constant=_reject_constant)
        rows = value if isinstance(value, list) else [value]
        if not rows or any(not isinstance(row, dict) for row in rows):
            raise ValueError("JSON must contain records")
        return len(rows)
    if suffix == ".jsonl":
        count = 0
        for line in text.splitlines():
            if line.strip():
                if not isinstance(json.loads(line, parse_constant=_reject_constant), dict):
                    raise ValueError("JSONL must contain objects")
                count += 1
        return count
    if suffix == ".csv":
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if (
            len(header) < 2
            or any(not key.strip() for key in header)
            or len(set(header)) != len(header)
        ):
            raise ValueError("CSV requires unique nonempty column names")
        count = 0
        for row in reader:
            if not row:
                continue
            if len(row) != len(header):
                raise ValueError("CSV row width does not match its header")
            count += 1
        if not count:
            raise ValueError("CSV requires data rows")
        return count
    return sum(bool(line.strip()) for line in text.splitlines())


def _metadata_name(filename: str) -> str:
    return f".{filename}.metadata"


def read_upload_metadata(path: Path) -> dict:
    """Read only bounded, regular, non-symlink metadata for generated uploads."""
    if not _GENERATED_NAME.fullmatch(path.name):
        return {}
    descriptor = os.open(path.parent, _DIRECTORY_FLAGS)
    try:
        try:
            fd = os.open(
                _metadata_name(path.name),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=descriptor,
            )
        except FileNotFoundError:
            return {}  # Legacy uploads predate metadata.
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Not a regular file")
            data = stream.read(16385)
        if len(data) > 16384:
            raise ValueError("Metadata exceeds limit")
        result = json.loads(data)
        if not isinstance(result, dict) or result.get("filename") != path.name:
            raise ValueError("Invalid metadata")
        return result
    except (OSError, ValueError) as exc:
        raise HTTPException(409, "Upload metadata is invalid") from exc
    finally:
        os.close(descriptor)


def delete_upload_metadata(path: Path) -> None:
    if _GENERATED_NAME.fullmatch(path.name):
        descriptor = os.open(path.parent, _DIRECTORY_FLAGS)
        try:
            try:
                os.unlink(_metadata_name(path.name), dir_fd=descriptor)
            except FileNotFoundError:
                pass
        finally:
            os.close(descriptor)


def store_upload(
    root: Path, file: UploadFile, name: str | None = None, *, display_name: str | None = None
) -> Path:
    original = file.filename or "upload.jsonl"
    # Preserve the legacy name-field rejection contract. The new display_name
    # field is explicitly metadata-only and may be sanitized independently.
    for value in (original, name or original):
        if not value or value in (".", "..") or any(c in value for c in "/\\\x00\r\n"):
            raise HTTPException(400, "Dataset name must be a plain filename")
    suffix = Path(original).suffix.lower()
    if suffix not in EXTENSIONS or (
        name and Path(name).suffix and Path(name).suffix.lower() != suffix
    ):
        raise HTTPException(400, "Unsupported dataset extension")
    final = uuid4().hex + suffix
    staging = ".upload-" + uuid4().hex
    with _raw_descriptor(root) as (directory, descriptor):
        try:
            fd = os.open(
                staging,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
        except FileExistsError as exc:
            raise HTTPException(409, "Upload storage collision") from exc
        metadata_created = False
        published = False
        try:
            size = 0
            digest = hashlib.sha256()
            with os.fdopen(fd, "w+b") as stream:
                while chunk := file.file.read(65536):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "Dataset exceeds 10 MiB")
                    digest.update(chunk)
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
                stream.seek(0)
                # Full-file validation; bounded by MAX_UPLOAD_BYTES, not a sniffed prefix.
                rows = _validate_content(stream.read().decode("utf-8"), suffix)
            metadata = {
                "filename": final,
                "display_name": sanitize_display_name(display_name or name or original),
                "sha256": digest.hexdigest(),
                "size_bytes": size,
                "format": suffix[1:],
                "row_count": rows,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Write metadata before publishing the payload. Hidden metadata is never
            # listed as a dataset. A process crash can leave an orphan sidecar.
            mfd = os.open(
                _metadata_name(final),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=descriptor,
            )
            metadata_created = True
            with os.fdopen(mfd, "w", encoding="utf-8") as stream:
                json.dump(metadata, stream, ensure_ascii=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.link(
                staging, final, src_dir_fd=descriptor, dst_dir_fd=descriptor, follow_symlinks=False
            )
            published = True
        except FileExistsError as exc:
            raise HTTPException(409, "Upload storage collision") from exc
        except (UnicodeError, ValueError, RecursionError, csv.Error, StopIteration) as exc:
            raise HTTPException(
                400, "Dataset content does not match the supported UTF-8 record format"
            ) from exc
        finally:
            os.unlink(staging, dir_fd=descriptor)
            if metadata_created and not published:
                os.unlink(_metadata_name(final), dir_fd=descriptor)
    return directory / final
