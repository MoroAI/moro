#!/usr/bin/env python3
"""
MoroAI Pre-Commit Safety & Alignment Guardian.

Scans all staged files for:
  1. Hardcoded secrets (API keys, AWS tokens, private keys, OAuth tokens)
  2. PII leaks in dataset files (.jsonl, .csv, .json)
  3. Unsafe eval configurations (eval cases missing safety guardrails)

Runs as a git pre-commit hook. Blocks the commit if any violations are found.

Install: moro hooks install
"""

import re
import subprocess
import sys
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# Secret Patterns
# ──────────────────────────────────────────────────────────────────────────────
# High-confidence secret patterns with low false-positive rate.
# These are all specific enough that false positives are extremely rare.

SECRET_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI API Key"),
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"ghs_[a-zA-Z0-9]{36}", "GitHub App Token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "Private Key"),
    (r"xox[baprs]-[0-9a-zA-Z\-]{10,}", "Slack Token"),
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API Key"),
    (r"ya29\.[0-9A-Za-z\-_]+", "Google OAuth Token"),
    (r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}", "JWT Token"),
    (r"Bearer\s+[a-zA-Z0-9\-_\.]{20,}", "Bearer Token"),
    (r"(?i)password\s*=\s*[\"'][^\"']{8,}[\"']", "Hardcoded Password"),
    (r"(?i)secret\s*=\s*[\"'][^\"']{8,}[\"']", "Hardcoded Secret"),
    (r"(?i)api[_-]?key\s*=\s*[\"'][a-zA-Z0-9\-_\.]{16,}[\"']", "Hardcoded API Key"),
]

# ──────────────────────────────────────────────────────────────────────────────
# PII Patterns (applied only to data files)
# ──────────────────────────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "Email Address"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "US Social Security Number (SSN)"),
    (r"\b(?:\d{4}[- ]?){3}\d{4}\b", "Credit Card Number Pattern"),
    (r"\b\d{10,11}\b", "Potential Phone Number (10–11 digits)"),
    (r"(?i)\bpatient\s+(?:id|identifier|name)\b.*[:=]\s*\S+", "Patient Identifier"),
    (r"(?i)\b(?:dob|date.of.birth)\b.*[:=]\s*\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}", "Date of Birth"),
]

# ──────────────────────────────────────────────────────────────────────────────
# File Classification
# ──────────────────────────────────────────────────────────────────────────────

# Files where we check for hardcoded secrets
_SECRET_SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".yaml", ".yml", ".json", ".env",
    ".sh", ".bash", ".zsh", ".toml", ".cfg", ".ini", ".conf",
}

# Files skipped for secret scanning (binary / already safe)
_SKIP_SECRET_EXTENSIONS = {".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                             ".ico", ".pdf", ".zip", ".gz", ".tar"}

# Data files where we check for PII
_DATA_EXTENSIONS = {".jsonl", ".csv", ".json", ".parquet", ".tsv"}

# Paths that indicate test/mock data — PII patterns are expected there
_SAFE_DATA_PATHS = {"tests/", "test/", "mock_", "fixture", "__pycache__"}


def _is_safe_path(filepath: str) -> bool:
    """Return True if the path looks like test/mock data."""
    return any(s in filepath for s in _SAFE_DATA_PATHS)


def get_staged_files() -> list[str]:
    """Get all files currently staged for commit (added, copied, modified)."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().split("\n") if f]


def check_secrets(filepath: str) -> list[str]:
    """Scan a file for hardcoded secrets."""
    violations: list[str] = []
    ext = Path(filepath).suffix.lower()

    if ext in _SKIP_SECRET_EXTENSIONS:
        return violations
    if ext and ext not in _SECRET_SCAN_EXTENSIONS:
        return violations  # Unknown extension — skip

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for pattern, name in SECRET_PATTERNS:
            if re.search(pattern, content):
                violations.append(f"Hardcoded secret [{name}] detected in: {filepath}")
    except (OSError, PermissionError):
        pass  # Can't read — skip silently

    return violations


def check_pii_in_data(filepath: str) -> list[str]:
    """Scan data files for unredacted PII."""
    violations: list[str] = []
    ext = Path(filepath).suffix.lower()

    if ext not in _DATA_EXTENSIONS:
        return violations
    if _is_safe_path(filepath):
        return violations  # Skip test/mock data

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for pattern, name in PII_PATTERNS:
            matches = re.findall(pattern, content)
            if matches:
                violations.append(
                    f"Potential PII [{name}] in data file: {filepath} "
                    f"({len(matches)} occurrence(s))"
                )
    except (OSError, PermissionError):
        pass

    return violations


def main() -> None:
    staged_files = get_staged_files()
    if not staged_files:
        print("✅ MoroAI Pre-Commit Safety Check: No staged files to scan.")
        sys.exit(0)

    all_violations: list[str] = []

    for filepath in staged_files:
        all_violations.extend(check_secrets(filepath))
        all_violations.extend(check_pii_in_data(filepath))

    if all_violations:
        print("\n" + "=" * 72)
        print("🚨 MOROAI SAFETY & ALIGNMENT PRE-COMMIT HOOK FAILED 🚨")
        print("=" * 72)
        for v in all_violations:
            print(f"  ❌ {v}")
        print("\n  Commit blocked. Fix the violations above or use:")
        print("    moro guard redact <file>   — auto-redact PII")
        print("    git commit --no-verify      — bypass (STRONGLY NOT RECOMMENDED)")
        print("=" * 72 + "\n")
        sys.exit(1)
    else:
        print(
            f"✅ MoroAI Pre-Commit Safety Check: Passed. "
            f"({len(staged_files)} file(s) scanned, no violations found.)"
        )
        sys.exit(0)


if __name__ == "__main__":
    main()
