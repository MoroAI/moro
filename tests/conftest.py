"""
Shared pytest fixtures for MoroAI tests.
"""

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal MoroAI project in a temp directory."""
    from moro.core.paths import ensure_project_dirs
    from moro.templates.project import SAMPLE_EVAL_YAML, default_moro_yaml, readme_template

    root = tmp_path / "test-project"
    root.mkdir()

    dirs = ensure_project_dirs(root)

    (root / "moro.yaml").write_text(default_moro_yaml("test-project"), encoding="utf-8")
    (root / "README.md").write_text(readme_template("test-project"), encoding="utf-8")
    (dirs["eval"] / "support-golden-v1.yaml").write_text(SAMPLE_EVAL_YAML, encoding="utf-8")

    return root


@pytest.fixture
def sample_jsonl(tmp_path: Path) -> Path:
    """Write a small JSONL chat dataset to a temp file."""
    rows = [
        {
            "messages": [
                {"role": "user", "content": "How do I reset my password?"},
                {
                    "role": "assistant",
                    "content": "Go to Settings > Security and click Reset Password.",
                },
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "What is your refund policy?"},
                {
                    "role": "assistant",
                    "content": "We offer a full refund within 14 days of purchase.",
                },
            ]
        },
        {
            "messages": [
                {"role": "system", "content": "You are a helpful support agent."},
                {"role": "user", "content": "I cannot log in."},
                {
                    "role": "assistant",
                    "content": "Please try resetting your password from the login page.",
                },
            ]
        },
    ]
    path = tmp_path / "support.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


@pytest.fixture
def sample_instruction_jsonl(tmp_path: Path) -> Path:
    """Write Alpaca-style instruction dataset."""
    rows = [
        {
            "instruction": "Summarize this text.",
            "input": "Long text here.",
            "output": "Short summary.",
        },
        {"instruction": "Translate to French.", "output": "Bonjour!"},
    ]
    path = tmp_path / "instructions.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path
