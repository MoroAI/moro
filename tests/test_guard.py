"""
Tests for moro guard and privacy redaction.
"""

from typer.testing import CliRunner

from moro.data.models import DatasetMessage, DatasetRow
from moro.data.privacy import redact_row, redact_rows, redact_text
from moro.main import app

runner = CliRunner()


def test_redact_text_replaces_pii():
    text = "Contact alice@example.com or call +1 555-234-5678. API key: sk-abcdef1234567890abcdef."
    redacted, flags = redact_text(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "[REDACTED_API_KEY]" in redacted
    assert "alice@example.com" not in redacted
    assert "email" in flags
    assert "phone" in flags
    assert "api_key" in flags


def test_redact_row_in_place():
    row = DatasetRow(
        id="r1",
        source="test",
        messages=[
            DatasetMessage(role="user", content="My SSN is 123-45-6789"),
            DatasetMessage(role="assistant", content="Acknowledged, user@domain.org"),
        ],
    )
    redacted_row, flags = redact_row(row)
    assert "[REDACTED_SSN]" in redacted_row.messages[0].content
    assert "[REDACTED_EMAIL]" in redacted_row.messages[1].content
    assert "ssn" in flags
    assert "email" in flags


def test_redact_rows_multiple():
    rows = [
        DatasetRow(
            id="r1",
            source="test",
            messages=[DatasetMessage(role="user", content="Call 555-123-4567")],
        ),
        DatasetRow(
            id="r2",
            source="test",
            messages=[DatasetMessage(role="user", content="No secrets here")],
        ),
    ]
    _, count = redact_rows(rows)
    assert count == 1
    assert "[REDACTED_PHONE]" in rows[0].messages[0].content
    assert rows[1].messages[0].content == "No secrets here"


def test_cli_guard_scan_clean(tmp_path):
    f = tmp_path / "clean.jsonl"
    f.write_text('{"messages": [{"role": "user", "content": "Hello world"}]}\n')
    result = runner.invoke(app, ["guard", "scan", str(f)])
    assert result.exit_code == 0
    assert "No PII or secrets detected" in result.stdout


def test_cli_guard_scan_detected(tmp_path):
    f = tmp_path / "dirty.jsonl"
    f.write_text('{"messages": [{"role": "user", "content": "Email me at bob@corp.com"}]}\n')
    result = runner.invoke(app, ["guard", "scan", str(f)])
    assert result.exit_code == 0
    assert "potential PII/secret matches found" in result.stdout
    assert "email" in result.stdout


def test_cli_guard_redact(tmp_path):
    src = tmp_path / "input.txt"
    src.write_text("Secret key sk-1234567890abcdef1234 here\n")
    out = tmp_path / "output.txt"
    result = runner.invoke(app, ["guard", "redact", str(src), "-o", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    content = out.read_text()
    assert "[REDACTED_API_KEY]" in content
    assert "sk-1234567890abcdef1234" not in content


def test_cli_guard_check(tmp_path):
    clean_f = tmp_path / "clean.txt"
    clean_f.write_text("All clean and safe.\n")
    res_clean = runner.invoke(app, ["guard", "check", str(clean_f)])
    assert res_clean.exit_code == 0

    dirty_f = tmp_path / "dirty.txt"
    dirty_f.write_text("API token sk-9876543210fedcba9876 present.\n")
    res_dirty = runner.invoke(app, ["guard", "check", str(dirty_f)])
    assert res_dirty.exit_code == 1
