"""Tests for data normalization."""

from moro.data.normalize import normalize_rows


def _make_raw(obj: dict, source: str = "test.jsonl", line: int = 1) -> dict:
    return {**obj, "_source_file": source, "_line_number": line, "_format": "jsonl"}


def test_normalize_messages_format():
    raw = [
        _make_raw(
            {
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"},
                ]
            }
        )
    ]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 1
    assert len(invalid) == 0
    assert valid[0].messages[0].role == "user"
    assert valid[0].messages[1].role == "assistant"


def test_normalize_instruction_format():
    raw = [
        _make_raw(
            {
                "instruction": "Summarize this text.",
                "input": "Long input text.",
                "output": "Short summary.",
            }
        )
    ]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 1
    msg_roles = [m.role for m in valid[0].messages]
    assert "user" in msg_roles
    assert "assistant" in msg_roles


def test_normalize_prompt_completion_format():
    raw = [
        _make_raw(
            {
                "prompt": "What is 2+2?",
                "completion": "4",
            }
        )
    ]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 1
    assert valid[0].messages[0].content == "What is 2+2?"
    assert valid[0].messages[1].content == "4"


def test_normalize_invalid_role():
    raw = [
        _make_raw(
            {
                "messages": [
                    {"role": "robot", "content": "Hello"},
                ]
            }
        )
    ]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 0
    assert len(invalid) == 1


def test_normalize_text_only_is_invalid():
    raw = [_make_raw({"text": "Just a plain text line."})]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 0
    assert len(invalid) == 1


def test_normalize_system_message_injected():
    raw = [
        _make_raw(
            {
                "system": "You are a helpful assistant.",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi!"},
                ],
            }
        )
    ]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 1
    assert valid[0].messages[0].role == "system"
    assert "helpful assistant" in valid[0].messages[0].content


def test_normalize_deduplicates_by_content():
    """Same row content produces the same ID."""
    row_obj = {
        "messages": [
            {"role": "user", "content": "Same question"},
            {"role": "assistant", "content": "Same answer"},
        ]
    }
    raw = [_make_raw(row_obj, line=1), _make_raw(row_obj, line=2)]
    valid, invalid = normalize_rows(raw, "test")
    assert len(valid) == 2
    assert valid[0].id == valid[1].id  # same content hash
