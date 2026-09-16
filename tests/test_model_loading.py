import sys
from types import SimpleNamespace

import pytest

from moro.core.errors import ConfigError, EvalError
from moro.eval import runner
from moro.models.loading import model_load_options, resolve_model_reference


def test_local_path_never_needs_hub(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    assert resolve_model_reference(str(tmp_path)) == str(tmp_path)


def test_cached_id_is_resolved_without_download(monkeypatch, tmp_path):
    calls = []

    def snapshot(reference, **options):
        calls.append((reference, options))
        return str(tmp_path)

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    assert resolve_model_reference("org/model", revision="abc") == str(tmp_path)
    assert calls == [("org/model", {"revision": "abc", "local_files_only": True})]


def test_cache_miss_does_not_fall_back_to_network(monkeypatch):
    def snapshot(*args, **kwargs):
        assert kwargs["local_files_only"] is True
        raise OSError("not cached")

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    with pytest.raises(ConfigError, match="not available in the local cache"):
        resolve_model_reference("org/model")


def test_external_mode_is_explicit():
    assert resolve_model_reference("org/model", local_only=False) == "org/model"
    assert model_load_options(local_only=True)["local_files_only"] is True
    with pytest.raises(ConfigError, match="trust_remote_code"):
        model_load_options(local_only=True, trust_remote_code=True)


def test_missing_absolute_path_is_not_a_hub_id(tmp_path):
    with pytest.raises(ConfigError, match="directory does not exist"):
        resolve_model_reference(str(tmp_path / "missing"), local_only=False)


def test_eval_loads_once_and_fails_on_generation_error(tmp_project, monkeypatch):
    loads = []
    calls = []

    def generator(messages, **kwargs):
        calls.append(messages)
        return [{"generated_text": [*messages, {"role": "assistant", "content": "support"}]}]

    def load(*args, **kwargs):
        loads.append(kwargs)
        return generator

    monkeypatch.setattr(runner, "_load_generator", load)
    suite = tmp_project / "eval/support-golden-v1.yaml"
    result = runner.run_suite(suite, "org/model")
    assert result.total_cases == 3
    assert len(loads) == 1
    assert loads[0]["local_only"] is True
    assert len(calls) == 3

    def fail(*args, **kwargs):
        raise RuntimeError("inference failed")

    monkeypatch.setattr(runner, "_generate_response", fail)
    with pytest.raises(EvalError, match="no quality result saved"):
        runner.run_suite(suite, "org/model")
