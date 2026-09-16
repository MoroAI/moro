"""Tests for the diagnostics analyzer."""

from moro.diagnose.analyzer import analyze_error


def test_oom_detected():
    diagnosis = analyze_error("RuntimeError: CUDA out of memory trying to allocate 2.5 GiB")
    assert "memory" in diagnosis["issue"].lower()
    assert any("batch_size" in action for action in diagnosis["actions"])


def test_nan_loss_detected():
    diagnosis = analyze_error("Training loss: nan at step 42")
    assert "nan" in diagnosis["issue"].lower() or "loss" in diagnosis["issue"].lower()
    assert any(
        "learning_rate" in action.lower() or "learning rate" in action.lower()
        for action in diagnosis["actions"]
    )


def test_dataset_error_detected():
    diagnosis = analyze_error("DatasetError: No valid rows remain after cleaning")
    assert "dataset" in diagnosis["issue"].lower()


def test_import_error_detected():
    diagnosis = analyze_error("ImportError: No module named 'bitsandbytes'")
    assert "dependency" in diagnosis["issue"].lower() or "missing" in diagnosis["issue"].lower()


def test_unknown_error_fallback():
    diagnosis = analyze_error("SomeRandomUnrecognizedError: something happened")
    assert "unknown" in diagnosis["issue"].lower() or "error" in diagnosis["issue"].lower()
    assert len(diagnosis["actions"]) > 0


def test_empty_error_handled():
    diagnosis = analyze_error("")
    assert diagnosis["issue"] is not None
