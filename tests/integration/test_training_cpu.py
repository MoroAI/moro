"""Real offline one-step training; enabled explicitly in the training CI job."""

import json
import os
import socket

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MORO_TRAINING_TESTS") != "1", reason="optional real training stack"
)


def test_offline_training_and_adapter_reload(tmp_path, monkeypatch):
    import torch
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

    from moro.config.models import MoroConfig
    from moro.eval.runner import _generate_response, _load_generator
    from moro.training.hf_backend import HuggingFaceBackend

    torch.set_num_threads(1)
    base = tmp_path / "base"
    base.mkdir()
    vocabulary = {
        word: index
        for index, word in enumerate(
            ["[UNK]", "[PAD]", "[EOS]", "user", "assistant", ":", "hello", "world", "hi"]
        )
    }
    raw = Tokenizer(WordLevel(vocabulary, unk_token="[UNK]"))
    raw.pre_tokenizer = Whitespace()
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=raw, unk_token="[UNK]", pad_token="[PAD]", eos_token="[EOS]"
    )
    tokenizer.chat_template = (
        "{% for message in messages %}{{ message['role'] + ': ' + message['content'] "
        "+ eos_token }}{% endfor %}{% if add_generation_prompt %}assistant: {% endif %}"
    )
    tokenizer.save_pretrained(base)
    model = GPT2LMHeadModel(
        GPT2Config(
            vocab_size=len(vocabulary),
            n_layer=1,
            n_head=2,
            n_embd=16,
            n_positions=64,
            eos_token_id=2,
            pad_token_id=1,
            bos_token_id=2,
        )
    )
    model.save_pretrained(base)
    rows = [
        dict(
            id=str(i),
            source="synthetic",
            messages=[
                dict(role="user", content="hello world"),
                dict(role="assistant", content="hi"),
            ],
        )
        for i in range(4)
    ]
    train = tmp_path / "train.jsonl"
    train.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (tmp_path / "validation.jsonl").write_text(train.read_text())
    cfg = MoroConfig.model_validate(
        dict(
            project=dict(name="offline-smoke", privacy_mode="local_only"),
            dataset=dict(source=str(train), max_seq_length=32),
            model=dict(name=str(base), quantization="none"),
            adapter=dict(r=2, alpha=4, target_modules=["c_attn"]),
            training=dict(
                max_steps=1,
                batch_size=1,
                gradient_accumulation_steps=1,
                gradient_checkpointing=False,
                optimizer="adamw_torch",
                precision="fp32",
                logging_steps=1,
                save_steps=1,
            ),
        )
    )

    def deny_network(*args, **kwargs):
        raise AssertionError("Network access attempted during offline training/evaluation")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    result = HuggingFaceBackend().train(cfg, train, tmp_path / "run", "smoke")
    assert result["train_loss"] is not None
    assert result["validation_loss"] is not None
    assert (tmp_path / "run/adapter/adapter_model.safetensors").exists()
    assert (tmp_path / "run/checkpoint-1/trainer_state.json").exists()
    generator = _load_generator(result["adapter_path"], local_only=True)
    response = _generate_response(generator, [{"role": "user", "content": "hello"}], 4)
    assert isinstance(response, str)
