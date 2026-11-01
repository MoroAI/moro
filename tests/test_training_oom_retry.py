"""One-shot OOM restart is the only documented automatic recovery path."""

import json
import sys
from types import SimpleNamespace as NS

import pytest

from moro.config.models import MoroConfig
from moro.core.errors import TrainingError
from moro.training import hf_backend


def _config(model_name="local-model", **training_overrides):
    training = dict(
        optimizer="adamw_torch",
        batch_size=4,
        gradient_accumulation_steps=2,
        gradient_checkpointing=False,
    )
    training.update(training_overrides)
    return MoroConfig.model_validate(
        dict(
            project=dict(name="test"),
            dataset=dict(source="train.jsonl", max_seq_length=2048),
            model=dict(name=model_name, quantization="none"),
            adapter=dict(r=16, alpha=32),
            training=training,
        )
    )


def test_fallback_reduces_microbatch_and_preserves_effective_batch():
    cfg = _config(batch_size=4, gradient_accumulation_steps=2)
    fallback, actions = hf_backend._oom_fallback_config(cfg)
    assert fallback is not None
    assert fallback.training.batch_size == 1
    assert fallback.training.gradient_accumulation_steps == 8
    assert actions == ["Reduced microbatch to 1; preserved effective batch size"]
    # The training objective is untouched.
    assert fallback.dataset.max_seq_length == 2048
    assert fallback.adapter.r == 16
    assert fallback.adapter.alpha == 32
    assert fallback.training.optimizer == "adamw_torch"
    # The caller's config is untouched.
    assert cfg.training.batch_size == 4
    assert cfg.training.gradient_accumulation_steps == 2


def test_fallback_enables_checkpointing_when_microbatch_is_already_one():
    cfg = _config(batch_size=1, gradient_checkpointing=False)
    fallback, actions = hf_backend._oom_fallback_config(cfg)
    assert fallback is not None
    assert fallback.training.gradient_checkpointing is True
    assert fallback.training.batch_size == 1
    assert actions == ["Enabled gradient checkpointing"]
    assert cfg.training.gradient_checkpointing is False


def test_no_fallback_when_nothing_objective_preserving_remains():
    cfg = _config(batch_size=1, gradient_checkpointing=True)
    fallback, actions = hf_backend._oom_fallback_config(cfg)
    assert fallback is None
    assert actions == []


def _install_fake_stack(monkeypatch, train_behavior):
    """Install stub torch/transformers/peft/trl modules like the backend tests."""
    attempts = []
    model = NS(
        config=NS(use_cache=True),
        print_trainable_parameters=lambda: None,
        save_pretrained=lambda path: None,
    )
    tokenizer = NS(
        chat_template="template",
        pad_token="pad",
        padding_side="left",
        save_pretrained=lambda path: None,
    )

    class Trainer:
        def __init__(self, **kwargs):
            attempts.append(kwargs)
            self.state = NS(log_history=[])

        def train(self):
            return train_behavior(len(attempts))

        def evaluate(self):
            return {}

    fake_modules = {
        "torch": NS(
            float32="fp32",
            float16="fp16",
            bfloat16="bf16",
            cuda=NS(
                is_available=lambda: False,
                is_bf16_supported=lambda: False,
                current_device=lambda: 0,
                reset_peak_memory_stats=lambda: None,
                max_memory_allocated=lambda: 0,
            ),
        ),
        "datasets": NS(Dataset=NS(from_list=lambda rows: rows)),
        "peft": NS(
            LoraConfig=lambda **kw: kw,
            TaskType=NS(CAUSAL_LM="causal"),
            get_peft_model=lambda model, config: model,
            prepare_model_for_kbit_training=lambda model, **kw: model,
        ),
        "transformers": NS(
            AutoModelForCausalLM=NS(from_pretrained=lambda *a, **kw: model),
            AutoTokenizer=NS(from_pretrained=lambda *a, **kw: tokenizer),
            BitsAndBytesConfig=lambda **kw: kw,
            set_seed=lambda seed: None,
        ),
        "trl": NS(SFTConfig=lambda **kw: kw, SFTTrainer=Trainer),
    }
    fake_modules["trl"].SFTConfig.__dataclass_fields__ = {"warmup_steps": None}
    for name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(hf_backend, "_require_imports", lambda cfg: None)
    return attempts


def _train_dataset(tmp_path):
    row = dict(
        id="one",
        source="test",
        messages=[dict(role="user", content="hi"), dict(role="assistant", content="hello")],
    )
    train = tmp_path / "train.jsonl"
    train.write_text(json.dumps(row) + "\n")
    return train


def test_oom_triggers_single_restart_with_preserved_effective_batch(tmp_path, monkeypatch):
    def behavior(attempt):
        if attempt == 1:
            raise RuntimeError("CUDA out of memory. Tried to allocate 2.5 GiB.")
        return NS(training_loss=0.5)

    attempts = _install_fake_stack(monkeypatch, behavior)
    cfg = _config(str(tmp_path), batch_size=4, gradient_accumulation_steps=2)
    train = _train_dataset(tmp_path)
    output_dir = tmp_path / "run"

    result = hf_backend.HuggingFaceBackend().train(cfg, train, output_dir, "oom-run")

    assert len(attempts) == 2
    assert result["oom_recovered"] is True
    assert result["recovery_kind"] == "restart"
    assert result["recovery_actions"] == ["Reduced microbatch to 1; preserved effective batch size"]
    retry_args = attempts[1]["args"]
    assert retry_args["per_device_train_batch_size"] == 1
    assert retry_args["gradient_accumulation_steps"] == 8
    assert result["effective_config"]["training"]["batch_size"] == 1
    assert result["effective_config"]["dataset"]["max_seq_length"] == 2048
    assert result["effective_config"]["adapter"]["r"] == 16
    requested = json.loads((output_dir / "requested-config.json").read_text())
    effective = json.loads((output_dir / "effective-config.json").read_text())
    assert requested["training"]["batch_size"] == 4
    assert effective["training"]["batch_size"] == 1


def test_second_oom_is_not_retried(tmp_path, monkeypatch):
    def behavior(attempt):
        raise RuntimeError("CUDA out of memory on every attempt")

    _install_fake_stack(monkeypatch, behavior)
    cfg = _config(str(tmp_path), batch_size=4)
    with pytest.raises(RuntimeError, match="out of memory"):
        hf_backend.HuggingFaceBackend().train(cfg, _train_dataset(tmp_path), tmp_path, "x")


def test_exhausted_retry_fails_with_training_error(tmp_path, monkeypatch):
    def behavior(attempt):
        raise RuntimeError("CUDA out of memory. Tried to allocate 2.5 GiB.")

    _install_fake_stack(monkeypatch, behavior)
    cfg = _config(str(tmp_path), batch_size=1, gradient_checkpointing=True)
    with pytest.raises(TrainingError, match="no objective-preserving automatic retry"):
        hf_backend.HuggingFaceBackend().train(cfg, _train_dataset(tmp_path), tmp_path, "x")


def test_non_oom_errors_are_never_rewritten(tmp_path, monkeypatch):
    def behavior(attempt):
        raise RuntimeError("NCCL timeout on rendezvous")

    attempts = _install_fake_stack(monkeypatch, behavior)
    with pytest.raises(RuntimeError, match="NCCL timeout"):
        hf_backend.HuggingFaceBackend().train(
            _config(str(tmp_path)), _train_dataset(tmp_path), tmp_path, "x"
        )
    assert len(attempts) == 1
