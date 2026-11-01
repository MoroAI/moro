"""Real offline one-step training; enabled explicitly in the training CI job."""

import json
import os
import socket
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("MORO_TRAINING_TESTS") != "1", reason="optional real training stack"
)


@pytest.mark.parametrize("entrypoint", ["backend", "sdk", "sdk_oom", "api"])
def test_offline_training_and_adapter_reload(tmp_path, monkeypatch, entrypoint):
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
                dict(role="user", content=f"hello world {i}"),
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
            dataset=dict(source=str(train), max_seq_length=32, deduplicate=False),
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

    if entrypoint == "sdk_oom":
        import weakref

        from trl import SFTTrainer

        original_train = SFTTrainer.train
        failed_trainer = []
        cfg.training.batch_size = 2

        def fail_once(trainer, *args, **kwargs):
            if not failed_trainer:
                failed_trainer.append(weakref.ref(trainer))
                raise RuntimeError("CUDA out of memory (controlled CPU fault injection)")
            assert failed_trainer[0]() is None, "Failed trainer retained across recovery"
            return original_train(trainer, *args, **kwargs)

        monkeypatch.setattr(SFTTrainer, "train", fail_once)

    def deny_network(*args, **kwargs):
        raise AssertionError("Network access attempted during offline training/evaluation")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    if entrypoint == "backend":
        result = HuggingFaceBackend().train(cfg, train, tmp_path / "run", "smoke")
        output = tmp_path / "run"
    else:
        from moro.config.models import EvalSuiteRef, ReleaseRequirements
        from moro.data.compiler import DataCompiler
        from moro.training.runner import TrainingRunner

        cfg.release.require = ReleaseRequirements(min_pass_rate=0, safety_pass=False)
        cfg.eval.suites = [EvalSuiteRef(path=Path("suite.yaml"))]
        (tmp_path / "moro.yaml").write_text(cfg.model_dump_json())
        version = DataCompiler(tmp_path).compile_dataset(train)
        if entrypoint == "api":
            from fastapi.testclient import TestClient

            from moro.dashboard.mission_control import mission_app

            monkeypatch.chdir(tmp_path)
            token = "offline-api-fixture-" + "a" * 32
            monkeypatch.setenv("MORO_API_TOKEN", token)
            client = TestClient(mission_app, base_url="http://127.0.0.1")
            response = client.post(
                "/api/operations/start_training",
                json={"dataset_id": version},
                headers={"Authorization": "Bearer " + token},
            )
            assert response.status_code == 200, response.text
            assert response.json()["ok"] is True
            result = response.json()["payload"]
        else:
            result = TrainingRunner(tmp_path).run_training(dataset_id=version)
        output = Path(result["output_dir"])

    assert result["train_loss"] is not None
    assert result["validation_loss"] is not None
    assert (output / "adapter/adapter_model.safetensors").exists()
    assert (output / "checkpoint-1/trainer_state.json").exists()
    generator = _load_generator(result["adapter_path"], local_only=True)
    response = _generate_response(generator, [{"role": "user", "content": "hello"}], 4)
    assert isinstance(response, str)

    if entrypoint in {"sdk", "sdk_oom", "api"}:
        from moro.eval import runner as eval_runner
        from moro.eval.harness import EvalHarness
        from moro.release.manager import ReleaseManager
        from moro.storage import db

        suite = tmp_path / "suite.yaml"
        suite.write_text(
            json.dumps(
                {
                    "name": "offline-contract",
                    "cases": [
                        {
                            "id": "known-failing-assertion",
                            "messages": [{"role": "user", "content": "hello"}],
                            "expect": {"contains": ["IMPOSSIBLE_TOKEN_NOT_IN_VOCAB"]},
                        }
                    ],
                }
            )
        )
        # Real inference, bounded to the tiny test model's context length.
        generate = eval_runner._generate_response
        monkeypatch.setattr(
            eval_runner,
            "_generate_response",
            lambda generator, messages: generate(generator, messages, 4),
        )
        evaluation = EvalHarness(tmp_path).run_evaluation(result["run_id"], suite)
        assert evaluation["pass_rate"] == 0.0
        assert evaluation["execution_kind"] == "model"
        conn = db.get_connection(tmp_path)
        assert conn.execute(
            "SELECT id FROM eval_runs WHERE id=?", (evaluation["eval_id"],)
        ).fetchone()
        conn.close()
        release = ReleaseManager(tmp_path).create_release(result["run_id"], "smoke")
        manifest = json.loads(Path(release["manifest_path"]).read_text())
        assert manifest["release_gate"]["status"] == "passed"
        assert manifest["dataset_version_id"] == version

        if entrypoint == "sdk_oom":
            assert result["oom_recovered"] is True
            effective = json.loads((output / "config.json").read_text())
            requested = json.loads((output / "requested-config.json").read_text())
            assert effective["training"]["batch_size"] == 1
            assert effective["training"]["gradient_accumulation_steps"] == 2
            assert requested["training"]["batch_size"] == 2
            assert effective["adapter"] == requested["adapter"]
            assert effective["dataset"] == requested["dataset"]
