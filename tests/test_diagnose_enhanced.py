"""Tests for the enhanced diagnose CLI — log scanning and improved formatting."""

from pathlib import Path

from moro.diagnose.analyzer import analyze_error


# ──────────────────────────────────────────────────────────────────────────────
# Analyzer pattern tests
# ──────────────────────────────────────────────────────────────────────────────

def test_oom_detected():
    diagnosis = analyze_error("RuntimeError: CUDA out of memory trying to allocate 2.5 GiB")
    assert "memory" in diagnosis["issue"].lower()
    assert any("batch_size" in action for action in diagnosis["actions"])
    assert "training.batch_size" in diagnosis["config_changes"]


def test_nan_loss_detected():
    diagnosis = analyze_error("Training loss: nan at step 42")
    assert "nan" in diagnosis["issue"].lower() or "loss" in diagnosis["issue"].lower()
    assert len(diagnosis["actions"]) > 0


def test_dataset_error_detected():
    diagnosis = analyze_error("DatasetError: No valid rows remain after cleaning")
    assert "dataset" in diagnosis["issue"].lower()


def test_import_error_detected():
    diagnosis = analyze_error("ImportError: No module named 'bitsandbytes'")
    assert "dependency" in diagnosis["issue"].lower() or "missing" in diagnosis["issue"].lower()


def test_unknown_error_fallback():
    diagnosis = analyze_error("SomeRandomUnrecognizedError: something happened")
    assert diagnosis["issue"] is not None
    assert len(diagnosis["actions"]) > 0


def test_empty_error_handled():
    diagnosis = analyze_error("")
    assert diagnosis["issue"] is not None
    assert "No error" in diagnosis["issue"] or diagnosis["issue"]


# ──────────────────────────────────────────────────────────────────────────────
# Log scanner tests
# ──────────────────────────────────────────────────────────────────────────────

def test_log_scanner_finds_traceback(tmp_path: Path):
    from moro.cli.diagnose import _extract_error_from_log

    output_dir = tmp_path / "run_abc"
    output_dir.mkdir()
    log_file = output_dir / "training.log"
    log_file.write_text(
        "Step 1/10...\nStep 2/10...\n"
        "Traceback (most recent call last):\n"
        "  File 'train.py', line 42, in run\n"
        "RuntimeError: CUDA out of memory.\n",
        encoding="utf-8",
    )

    result = _extract_error_from_log(output_dir)
    assert result is not None
    assert "CUDA out of memory" in result


def test_log_scanner_finds_training_report(tmp_path: Path):
    import json as _json
    from moro.cli.diagnose import _extract_error_from_log

    output_dir = tmp_path / "run_def"
    output_dir.mkdir()
    report = output_dir / "training_report.json"
    report.write_text(_json.dumps({"error": "loss became nan at step 5"}))

    result = _extract_error_from_log(output_dir)
    assert result is not None
    assert "nan" in result


def test_log_scanner_returns_none_for_empty_dir(tmp_path: Path):
    from moro.cli.diagnose import _extract_error_from_log

    output_dir = tmp_path / "empty_run"
    output_dir.mkdir()

    result = _extract_error_from_log(output_dir)
    assert result is None


def test_log_scanner_returns_none_for_nonexistent(tmp_path: Path):
    from moro.cli.diagnose import _extract_error_from_log

    result = _extract_error_from_log(tmp_path / "nonexistent")
    assert result is None
