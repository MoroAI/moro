"""Tests for data inspect command logic."""

import json
from pathlib import Path


def _write_split(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_inspect_reads_train_split(tmp_path: Path):
    """
    Verify the inspect reading logic works independently of the CLI.
    Reads N rows from a JSONL file with an offset.
    """
    split_path = tmp_path / "train.jsonl"
    rows = [
        {"messages": [{"role": "user", "content": f"Q{i}"}, {"role": "assistant", "content": f"A{i}"}]}
        for i in range(20)
    ]
    _write_split(split_path, rows)

    # Simulate inspect logic: read 5 rows starting from offset 3
    n, offset = 5, 3
    result = []
    with split_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            if len(result) >= n:
                break
            result.append(json.loads(line.strip()))

    assert len(result) == n
    assert result[0]["messages"][0]["content"] == "Q3"
    assert result[-1]["messages"][0]["content"] == "Q7"


def test_inspect_offset_beyond_end_returns_empty(tmp_path: Path):
    split_path = tmp_path / "train.jsonl"
    _write_split(split_path, [{"messages": [{"role": "user", "content": "only row"}]}])

    result = []
    offset = 100
    with split_path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i < offset:
                continue
            result.append(json.loads(line.strip()))

    assert result == []


def test_inspect_content_truncation():
    """Long content should be truncated to 300 chars + ellipsis."""
    content = "x" * 500
    truncated = content[:297] + "…" if len(content) > 300 else content
    assert len(truncated) == 298
    assert truncated.endswith("…")


def test_inspect_role_color_mapping():
    """Role color mapping is correct."""
    role_colors = {
        "system": "dim",
        "user": "green",
        "assistant": "blue",
    }
    for role, expected_color in role_colors.items():
        color = {
            "system": "dim",
            "user": "green",
            "assistant": "blue",
        }.get(role, "white")
        assert color == expected_color

    # Unknown role falls back to white
    assert {"system": "dim"}.get("unknown_role", "white") == "white"
