# Training integration and offline loading

## Reference environment

The training extra pins a reference stack: torch 2.8.0, transformers 4.56.2, TRL 0.23.1, PEFT 0.17.1, datasets 4.1.1, and accelerate 1.10.1. The core CLI remains independent of these packages. Use Python 3.11 on Linux for the integration job; this is not a claim of training support on every Python/platform combination accepted by the core CLI.

```bash
python -m pip install -e '.[dev,train]'
MORO_TRAINING_TESTS=1 HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1 python -m pytest tests/integration -v
```

For CUDA quantized training, install `.[train,cuda]`, which adds bitsandbytes 0.47.0. CUDA and MPS still need real hardware validation. CPU training uses `model.quantization: none`, `training.optimizer: adamw_torch`, and `training.precision: fp32`.

## Behavior

- Training passes conversational rows to TRL with the tokenizer's chat template. Missing templates fail explicitly. The current objective trains on all conversation tokens, not assistant-only tokens.
- SFTConfig carries sequence length; SFTTrainer receives the tokenizer through `processing_class`.
- Quantized models are prepared for k-bit training before LoRA is applied. Quantized placement targets the current CUDA device; unquantized placement is handled by Trainer.
- Validation uses the neighboring nonempty `validation.jsonl`, runs at epoch boundaries, and is explicitly evaluated after training.
- Project seed is applied before model loading. Throughput is reported only when the trainer supplies a measured token count.
- Trainer saves checkpoints; CLI resume remains explicitly unsupported pending lineage and compatibility validation.

The API migration follows [TRL 0.23.1 SFT documentation](https://huggingface.co/docs/trl/v0.23.1/en/sft_trainer) and [PEFT quantization guidance](https://huggingface.co/docs/peft/developer_guides/quantization).

## Local-only mode

`project.privacy_mode: local_only` resolves model IDs against the local Hugging Face snapshot cache and passes local-files-only options to model/tokenizer loaders. A missing cache entry fails without a download fallback. Absolute or explicit relative paths must exist. Remote-code execution is rejected for training in local-only mode.

Evaluation loads a pipeline once per suite, loads adapters explicitly over their recorded base model, and uses chat-formatted generation. Adapter and base-model resolution both obey local-only mode. Model/inference errors abort evaluation instead of being persisted as model quality scores.

`allow_external` explicitly permits model downloads. This policy governs Moro's model loading; it is not a network sandbox for arbitrary third-party code. An isolated environment is appropriate when OS-level network enforcement is required. See [Transformers offline loading](https://huggingface.co/docs/transformers/installation#offline-mode).

## Evidence and limits

The optional CPU integration test creates a tiny random GPT-2 model and tokenizer on disk, trains a LoRA adapter for one optimizer step, checks validation loss and a checkpoint, then reloads the adapter and generates a response. Socket connections are rejected during training and evaluation. No pretrained weights or datasets are downloaded by the test.

This exercises real trainer APIs and adapter serialization, not model quality, CUDA quantization, VRAM estimates, deployment, or release approval. Those require separate acceptance runs.
