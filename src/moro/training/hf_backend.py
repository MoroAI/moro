"""
Hugging Face QLoRA training backend.

Wraps: transformers + peft + trl + bitsandbytes + accelerate.
Supports NF4 4-bit quantization + LoRA adapters.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from moro.config.models import MoroConfig
from moro.core.errors import DependencyError, TrainingError
from moro.training.backend import TrainingBackend


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

    def estimate_memory(self, config: MoroConfig) -> float:
        """Rough VRAM estimate in GB based on model size and quantization."""
        name = config.model.name.lower()
        quantization = config.model.quantization

        # Model parameter size heuristics (unquantized)
        param_gb = 14.0  # default 7B
        if "0.5b" in name or "500m" in name:
            param_gb = 1.0
        elif "1b" in name or "1.5b" in name:
            param_gb = 3.0
        elif "3b" in name:
            param_gb = 6.0
        elif "7b" in name or "8b" in name:
            param_gb = 14.0
        elif "13b" in name:
            param_gb = 26.0

        # Quantization factor
        factor = {"nf4": 0.25, "int8": 0.5, "none": 1.0}.get(quantization, 0.25)
        lora_overhead = 0.5  # adapters
        grad_overhead = 1.0 if config.training.gradient_checkpointing else 2.0

        return round(param_gb * factor + lora_overhead + grad_overhead, 1)

    def train(
        self,
        config: MoroConfig,
        dataset_path: Path,
        output_dir: Path,
        run_id: str,
        dry_run: bool = False,
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

        training_args = SFTConfig(
            output_dir=str(output_dir),
            num_train_epochs=config.training.epochs,
            max_steps=config.training.max_steps or -1,
            per_device_train_batch_size=config.training.batch_size,
            gradient_accumulation_steps=config.training.gradient_accumulation_steps,
            learning_rate=config.training.learning_rate,
            optim=config.training.optimizer,
            gradient_checkpointing=config.training.gradient_checkpointing,
            warmup_ratio=config.training.warmup_ratio,
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
        trainer_result = trainer.train()
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
        }
