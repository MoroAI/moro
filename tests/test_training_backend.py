"""Control-path regressions; the separate integration test uses real libraries."""

import json
import sys
from types import SimpleNamespace as NS

import pytest

from moro.config.models import MoroConfig
from moro.training import hf_backend


@pytest.mark.parametrize("quantization", ["nf4", "none"])
def test_training_api_wiring_and_zero_losses(tmp_path, monkeypatch, quantization):
    events = []
    options = {}
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

    def load_model(reference, **kwargs):
        options["model"] = kwargs
        return model

    def prepare(model, **kwargs):
        events.append("prepare")
        return model

    def adapt(model, config):
        events.append("lora")
        return model

    class Trainer:
        def __init__(self, **kwargs):
            options["trainer"] = kwargs
            self.state = NS(log_history=[{"num_tokens": 10}])

        def train(self):
            return NS(training_loss=0.0)

        def evaluate(self):
            events.append("evaluate")
            return {"eval_loss": 0.0}

    fake_modules = {
        "torch": NS(
            float32="fp32",
            float16="fp16",
            bfloat16="bf16",
            cuda=NS(
                is_available=lambda: quantization == "nf4",
                is_bf16_supported=lambda: True,
                current_device=lambda: 0,
                reset_peak_memory_stats=lambda: None,
                max_memory_allocated=lambda: 0,
            ),
        ),
        "datasets": NS(Dataset=NS(from_list=lambda rows: rows)),
        "peft": NS(
            LoraConfig=lambda **kw: kw,
            TaskType=NS(CAUSAL_LM="causal"),
            get_peft_model=adapt,
            prepare_model_for_kbit_training=prepare,
        ),
        "transformers": NS(
            AutoModelForCausalLM=NS(from_pretrained=load_model),
            AutoTokenizer=NS(from_pretrained=lambda *a, **kw: tokenizer),
            BitsAndBytesConfig=lambda **kw: kw,
            set_seed=lambda seed: None,
        ),
        "trl": NS(SFTConfig=lambda **kw: kw, SFTTrainer=Trainer),
    }
    for name, module in fake_modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(hf_backend, "_require_imports", lambda cfg: None)
    row = dict(
        id="one",
        source="test",
        messages=[dict(role="user", content="hi"), dict(role="assistant", content="hello")],
    )
    train = tmp_path / "train.jsonl"
    train.write_text(json.dumps(row) + "\n")
    (tmp_path / "validation.jsonl").write_text(train.read_text())
    cfg = MoroConfig.model_validate(
        dict(
            project=dict(name="test"),
            dataset=dict(source=str(train)),
            model=dict(name=str(tmp_path), quantization=quantization),
            training=dict(optimizer="adamw_torch"),
        )
    )
    result = hf_backend.HuggingFaceBackend().train(cfg, train, tmp_path / "run", "test")
    assert result["train_loss"] == result["validation_loss"] == 0.0
    assert options["model"]["local_files_only"] is True
    trainer = options["trainer"]
    assert trainer["processing_class"] is tokenizer
    assert trainer["args"]["max_length"] == cfg.dataset.max_seq_length
    assert trainer["args"]["eval_strategy"] == "epoch"
    assert trainer["train_dataset"] == [{"messages": row["messages"]}]
    if quantization == "nf4":
        assert events == ["prepare", "lora", "evaluate"]
        assert options["model"]["device_map"] == {"": 0}
    else:
        assert events == ["lora", "evaluate"]
        assert "device_map" not in options["model"]
