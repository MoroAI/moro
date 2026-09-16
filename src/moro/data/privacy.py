"""
Privacy scanner — regex-based PII and secret detection for MVP.
Flags rows that may contain:
  - email addresses
  - phone numbers
  - API keys / tokens
  - private keys / secrets
  - credit card numbers
  - SSN patterns
"""

import re

from moro.data.models import DatasetRow

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}\b")),
    ("phone", re.compile(r"\b(\+?1[\s.-])?(\(?\d{3}\)?[\s.-])?\d{3}[\s.-]\d{4}\b")),
    ("api_key", re.compile(r"\b(sk-|pk-|api[-_]?key[-_]?)[a-zA-Z0-9_\-]{16,}\b", re.IGNORECASE)),
    ("bearer_token", re.compile(r"\bBearer\s+[a-zA-Z0-9_\-\.]+\b")),
    ("private_key", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "secret_env",
        re.compile(
            r"\b(password|passwd|secret|token|credential)[\s]*[=:]\s*['\"]?\S{6,}['\"]?",
            re.IGNORECASE,
        ),
    ),
    (
        "credit_card",
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11})\b"
        ),
    ),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
]


def scan_row(row: DatasetRow) -> list[str]:
    """
    Scan a DatasetRow for PII/secret patterns.
    Returns a list of flag strings like ['email', 'phone'].
    """
    full_text = " ".join(m.content for m in row.messages)
    flags: list[str] = []

    for flag_name, pattern in _PATTERNS:
        if pattern.search(full_text):
            flags.append(flag_name)

    return flags


def scan_rows(rows: list[DatasetRow]) -> list[DatasetRow]:
    """
    Scan all rows and populate their privacy_flags field in-place.
    Returns the same list with flags updated.
    """
    for row in rows:
        row.privacy_flags = scan_row(row)
    return rows
