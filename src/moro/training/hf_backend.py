"""
Hugging Face QLoRA training backend.

Wraps: transformers + peft + trl + bitsandbytes + accelerate.
Supports NF4 4-bit quantization + LoRA adapters.

A bounded, one-shot OOM restart reduces microbatch size while preserving
effective batch, or enables gradient checkpointing. It never silently changes
sequence length, LoRA rank, target modules, or the optimizer. When neither
objective-preserving retry is available, training fails with a TrainingError.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from moro.config.models import MoroConfig
from moro.core.errors import DependencyError, TrainingError
from moro.training.backend import TrainingBackend


def _oom_fallback_config(config: MoroConfig) -> tuple[MoroConfig | None, list[str]]:
    """Plan the single objective-preserving OOM retry, if one exists.

    Returns (fallback_config, actions). The fallback either shrinks the
    microbatch to 1 while scaling gradient accumulation to preserve the
    effective batch size, or enables gradient checkpointing. Sequence
    length, LoRA rank, target modules, and the optimizer are never
    changed. Returns (None, []) when no automatic retry is available.
    """
    if config.training.batch_size > 1:
        fallback = config.model_copy(deep=True)
        fallback.training.batch_size = 1
        fallback.training.gradient_accumulation_steps *= config.training.batch_size
        return fallback, ["Reduced microbatch to 1; preserved effective batch size"]
    if not config.training.gradient_checkpointing:
        fallback = config.model_copy(deep=True)
        fallback.training.gradient_checkpointing = True
        return fallback, ["Enabled gradient checkpointing"]
    return None, []


def _require_imports(config: MoroConfig) -> None:
    """Raise a friendly error if training deps are missing."""
    missing = []
    packages = ["torch", "transformers", "datasets", "peft", "trl", "accelerate"]
    if config.model.quantization != "none" or "8bit" in config.training.optimizer:
        packages.append("bitsandbytes")
    for pkg in packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise DependencyError(
            f"Missing training dependencies: {', '.join(missing)}\n"
            "Install moroai[train]; add moroai[cuda] for quantization or 8-bit optimizers."
        )


class HuggingFaceBackend(TrainingBackend):
    """QLoRA training backend using Hugging Face stack."""

    def validate(self, config: MoroConfig, dataset_path: Path) -> list[str]:
        warnings: list[str] = []

        if not dataset_path.exists():
            raise TrainingError(f"Training dataset not found: {dataset_path}")

        # Check row count
        from pydantic import ValidationError

        from moro.data.models import DatasetRow

        row_count = 0
        with dataset_path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    row = DatasetRow.model_validate_json(line)
                except ValidationError as exc:
                    raise TrainingError(f"Invalid training row at line {line_number}.") from exc
                roles = {message.role for message in row.messages}
                if not {"user", "assistant"}.issubset(roles) or any(
                    not message.content.strip() for message in row.messages
                ):
                    raise TrainingError(f"Incomplete training row at line {line_number}.")
                row_count += 1
        if row_count == 0:
            raise TrainingError("Training dataset is empty.")
        if row_count < 10:
            warnings.append(f"Very small training set ({row_count} rows) — results may be poor.")

        return warnings

    def estimate_memory(self, config: MoroConfig) -> float | None:
        from moro.recipes.rules import estimate_config_memory

        return estimate_config_memory(config)

    def train(
        self,
        config: MoroConfig,
        dataset_path: Path,
        output_dir: Path,
        run_id: str,
        dry_run: bool = False,
        _allow_recovery: bool = True,
    ) -> dict:
        self.validate(config, dataset_path)
        if dry_run:
            est_vram = self.estimate_memory(config)
            return {
                "dry_run": True,
                "estimated_vram_gb": est_vram,
                "model": config.model.name,
                "quantization": config.model.quantization,
            }

        _require_imports(config)

        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            set_seed,
        )
        from trl import SFTConfig, SFTTrainer

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        from moro.models.loading import model_load_options, resolve_model_reference

        local_only = config.project.privacy_mode == "local_only"
        options = model_load_options(
            local_only=local_only, trust_remote_code=config.model.trust_remote_code
        )
        cuda = torch.cuda.is_available()
        quantized = config.model.quantization != "none"
        if not cuda and (quantized or "8bit" in config.training.optimizer):
            raise TrainingError(
                "This backend requires CUDA for quantization or 8-bit optimizers. "
                "For CPU/MPS use quantization: none and optimizer: adamw_torch."
            )
        precision = config.training.precision
        supports_bf16 = cuda and torch.cuda.is_bf16_supported()
        if precision == "bf16" and not supports_bf16:
            raise TrainingError("Requested bf16 requires a supported CUDA device in this backend.")
        if precision == "fp16" and not cuda:
            raise TrainingError("Requested fp16 requires CUDA in this backend.")
        bf16 = precision == "bf16" or (precision == "auto" and supports_bf16)
        fp16 = precision == "fp16" or (precision == "auto" and cuda and not bf16)
        dtype = torch.bfloat16 if bf16 else torch.float16 if fp16 else torch.float32
        set_seed(config.project.seed)
        reference = resolve_model_reference(
            config.model.name, local_only=local_only, revision=config.model.revision
        )
        bnb_config = None
        if config.model.quantization == "nf4":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=dtype,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
            )
        elif config.model.quantization == "int8":
            bnb_config = BitsAndBytesConfig(load_in_8bit=True)

        tokenizer = AutoTokenizer.from_pretrained(
            reference, revision=config.model.revision, **options
        )
        if not tokenizer.chat_template:
            raise TrainingError(
                "The tokenizer must define a chat template for conversation training."
            )
        if tokenizer.pad_token is None:
            if tokenizer.eos_token is None:
                raise TrainingError("The tokenizer needs a padding or end-of-sequence token.")
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"
        model_options = {"torch_dtype": dtype, **options}
        if quantized:
            model_options.update(
                quantization_config=bnb_config, device_map={"": torch.cuda.current_device()}
            )
        model = AutoModelForCausalLM.from_pretrained(
            reference, revision=config.model.revision, **model_options
        )
        model.config.use_cache = False
        if quantized:
            model = prepare_model_for_kbit_training(
                model, use_gradient_checkpointing=config.training.gradient_checkpointing
            )

        # --- LoRA config ---
        target_modules = (
            config.adapter.target_modules
            if config.adapter.target_modules != "auto"
            else None  # let PEFT auto-detect
        )
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config.adapter.r,
            lora_alpha=config.adapter.alpha,
            target_modules=target_modules,
            lora_dropout=config.adapter.dropout,
            bias=config.adapter.bias,
        )
        model = get_peft_model(model, lora_config)
        model.print_trainable_parameters()

        # --- Load dataset ---
        def load_jsonl(path: Path) -> Dataset:
            rows = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    rows.append({"messages": json.loads(line)["messages"]})
            return Dataset.from_list(rows)

        train_dataset = load_jsonl(dataset_path)

        # Check for validation set
        val_dataset = None
        val_path = dataset_path.parent / "validation.jsonl"
        if val_path.exists() and val_path.stat().st_size:
            self.validate(config, val_path)
            val_dataset = load_jsonl(val_path)

        # Transformers 5 uses fractional warmup_steps in place of warmup_ratio.
        import math

        warmup = (
            {"warmup_ratio": config.training.warmup_ratio}
            if "warmup_ratio" in SFTConfig.__dataclass_fields__
            else {"warmup_steps": min(config.training.warmup_ratio, math.nextafter(1.0, 0.0))}
        )
        training_args = SFTConfig(
            output_dir=str(output_dir),
            num_train_epochs=config.training.epochs,
            max_steps=config.training.max_steps or -1,
            per_device_train_batch_size=config.training.batch_size,
            gradient_accumulation_steps=config.training.gradient_accumulation_steps,
            learning_rate=config.training.learning_rate,
            weight_decay=config.training.weight_decay,
            optim=config.training.optimizer,
            gradient_checkpointing=config.training.gradient_checkpointing,
            **warmup,
            logging_steps=config.training.logging_steps,
            save_steps=config.training.save_steps,
            save_total_limit=2,
            bf16=bf16,
            fp16=fp16,
            report_to="none",  # no wandb / cloud logging
            run_name=run_id,
            seed=config.project.seed,
            data_seed=config.project.seed,
            max_length=config.dataset.max_seq_length,
            packing=False,
            eval_strategy="epoch" if val_dataset is not None else "no",
            per_device_eval_batch_size=config.training.batch_size,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            push_to_hub=False,
        )

        # --- SFT Trainer ---
        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            processing_class=tokenizer,
        )

        if cuda:
            torch.cuda.reset_peak_memory_stats()
        start = time.time()

        recovered_config = None
        recovery_actions = []
        oom_recovered = False
        try:
            trainer_result = trainer.train()
        except RuntimeError as exc:
            if "out of memory" not in str(exc).lower() or not _allow_recovery:
                raise
            recovered_config, recovery_actions = _oom_fallback_config(config)
            if recovered_config is None:
                raise TrainingError(
                    "Out of memory; no objective-preserving automatic retry is available"
                ) from exc
        # Leave the exception scope before destroying the old trainer: its traceback
        # otherwise keeps optimizer/model references alive during the replacement load.
        if recovered_config is not None:
            import gc

            del trainer, model
            gc.collect()
            if cuda:
                torch.cuda.empty_cache()
            (output_dir / "requested-config.json").write_text(config.model_dump_json(indent=2))
            (output_dir / "effective-config.json").write_text(
                recovered_config.model_dump_json(indent=2)
            )
            result = self.train(
                recovered_config, dataset_path, output_dir, run_id, _allow_recovery=False
            )
            result.update(
                oom_recovered=True,
                recovery_actions=recovery_actions,
                recovery_kind="restart",
                effective_config=recovered_config.model_dump(mode="json"),
            )
            return result
        elapsed = time.time() - start

        # Save adapter
        adapter_dir = output_dir / "adapter"
        adapter_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(adapter_dir))
        tokenizer.save_pretrained(str(adapter_dir))

        # Extract metrics
        train_loss = (
            trainer_result.training_loss if hasattr(trainer_result, "training_loss") else None
        )
        val_loss = trainer.evaluate().get("eval_loss") if val_dataset is not None else None
        peak_vram = round(torch.cuda.max_memory_allocated() / (1024**3), 2) if cuda else None
        # Only report token throughput when the trainer actually counted tokens.
        measured_tokens = next(
            (
                entry["num_tokens"]
                for entry in reversed(trainer.state.log_history)
                if "num_tokens" in entry
            ),
            None,
        )
        tokens_per_sec = (
            round(measured_tokens / elapsed, 1)
            if measured_tokens is not None and elapsed > 0
            else None
        )

        return {
            "train_loss": round(train_loss, 4) if train_loss is not None else None,
            "validation_loss": round(val_loss, 4) if val_loss is not None else None,
            "peak_vram_gb": peak_vram,
            "tokens_per_sec": tokens_per_sec,
            "adapter_path": str(adapter_dir),
            "elapsed_seconds": round(elapsed, 1),
            "oom_recovered": oom_recovered,
            "recovery_actions": recovery_actions,
        }
