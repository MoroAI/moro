"""
Tests for MoroAI DevSecOps hooks and safety scanner.
"""

import sys
from pathlib import Path

from typer.testing import CliRunner

from moro.main import app

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "hooks"))
from pre_commit_safety_check import check_pii_in_data, check_secrets

runner = CliRunner()


def test_check_secrets_detects_openai_key(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('API_KEY = "sk-1234567890abcdef1234567890abcdef1234"\n')
    violations = check_secrets(str(f))
    assert len(violations) > 0
    assert "OpenAI API Key" in violations[0]


def test_check_secrets_clean_code(tmp_path):
    f = tmp_path / "app.py"
    f.write_text('import os\nAPI_KEY = os.environ.get("OPENAI_API_KEY")\n')
    violations = check_secrets(str(f))
    assert len(violations) == 0


def test_check_pii_in_data(tmp_path):
    f = tmp_path / "data.jsonl"
    f.write_text('{"user": "patient", "text": "DOB: 12/04/1985 SSN: 000-12-3456"}\n')
    violations = check_pii_in_data(str(f))
    assert len(violations) > 0


def test_check_pii_ignores_test_paths(tmp_path):
    test_dir = tmp_path / "tests" / "fixtures"
    test_dir.mkdir(parents=True)
    f = test_dir / "sample.jsonl"
    f.write_text('{"text": "email@example.com"}\n')
    violations = check_pii_in_data(str(f))
    assert len(violations) == 0  # safe path ignored


def test_cli_hooks_help():
    res = runner.invoke(app, ["hooks", "--help"])
    assert res.exit_code == 0
    assert "Git hooks and repository governance" in res.stdout
