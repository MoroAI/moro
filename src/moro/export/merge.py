"""
Merge a LoRA adapter into the base model weights to produce a standalone merged model.

The merged model is fully independent of PEFT/bitsandbytes — loadable with vanilla
transformers for inference or subsequent quantization.
"""

from __future__ import annotations

from pathlib import Path

from moro.core.errors import DependencyError, ExportError


def merge_adapter_into_base(
    adapter_path: Path,
    output_dir: Path,
    *,
    local_only: bool = True,
    torch_dtype: str = "auto",
) -> Path:
    """
    Merge a PEFT LoRA adapter into its base model and save the result.

    Args:
        adapter_path: Path to the saved adapter directory (contains adapter_config.json).
        output_dir: Directory to write the merged model into.
        local_only: Whether to restrict model loading to local cache.
        torch_dtype: dtype string for loading ("auto", "float16", "bfloat16", "float32").

    Returns:
        Path to the merged model directory.
    """
    try:
        import torch
        from peft import PeftConfig, PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise DependencyError(
            "Install moroai[train] to merge adapters (needs transformers, peft, torch)."
        ) from exc

    adapter_path = Path(adapter_path).resolve()
    output_dir = Path(output_dir)

    if not adapter_path.is_dir():
        raise ExportError(f"Adapter directory not found: {adapter_path}")

    adapter_cfg_path = adapter_path / "adapter_config.json"
    if not adapter_cfg_path.exists():
        raise ExportError(f"Not a valid adapter directory (missing adapter_config.json): {adapter_path}")

    from moro.models.loading import model_load_options, resolve_model_reference

    load_opts = model_load_options(local_only=local_only)
    peft_config = PeftConfig.from_pretrained(str(adapter_path), local_files_only=local_only)
    base_model_name = peft_config.base_model_name_or_path

    base_ref = resolve_model_reference(base_model_name, local_only=local_only)

    # Determine dtype
    dtype_map = {
        "auto": None,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    if torch_dtype not in dtype_map:
        raise ExportError(f"Invalid torch_dtype: {torch_dtype}. Choose auto, float16, bfloat16, or float32.")
    dtype = dtype_map[torch_dtype]

    model_kwargs = {**load_opts}
    if dtype is not None:
        model_kwargs["torch_dtype"] = dtype

    # Load base model — unquantized for clean merge
    base_model = AutoModelForCausalLM.from_pretrained(base_ref, **model_kwargs)
    tokenizer = AutoTokenizer.from_pretrained(base_ref, **load_opts)

    # Load adapter on top of base
    model = PeftModel.from_pretrained(base_model, str(adapter_path), local_files_only=local_only)

    # Merge and unload adapter weights into base
    model = model.merge_and_unload()
    model.eval()

    # Save merged model
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    return output_dir
