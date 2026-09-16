from __future__ import annotations

import platform
import shutil
import sys
from typing import Literal

import psutil


def _get_vram_gb() -> tuple[
    float | None, str | None, Literal["nvidia", "amd", "apple", "cpu", "unknown"]
]:
    """
    Attempt to detect GPU VRAM. Returns (vram_gb, gpu_name, vendor).
    Falls back gracefully if torch is not installed.
    """
    try:
        import torch  # noqa: PLC0415

        # CUDA (NVIDIA)
        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            vram = torch.cuda.get_device_properties(idx).total_memory / (1024**3)
            name = torch.cuda.get_device_name(idx)
            vendor: Literal["nvidia", "amd", "apple", "cpu", "unknown"] = "nvidia"
            # AMD may report via CUDA-HIP
            if "amd" in name.lower() or "radeon" in name.lower():
                vendor = "amd"
            return round(vram, 2), name, vendor

        # Apple Silicon MPS
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # MPS shares RAM — approximate from total system RAM
            total_ram = psutil.virtual_memory().total / (1024**3)
            approx_vram = round(total_ram * 0.75, 1)  # rough heuristic
            cpu_name = platform.processor() or "Apple Silicon"
            return approx_vram, cpu_name, "apple"

    except ImportError:
        pass
    except Exception:
        pass

    return None, None, "cpu"


def detect_hardware() -> dict:
    """
    Detect the local hardware profile and return a raw dict.
    """
    vram_gb, gpu_name, gpu_vendor = _get_vram_gb()

    # PyTorch
    torch_version = None
    cuda_available = False
    try:
        import torch  # noqa: PLC0415

        torch_version = torch.__version__
        cuda_available = torch.cuda.is_available()
    except ImportError:
        pass

    # System RAM
    cpu_ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)

    # Disk free (project drive)
    disk = shutil.disk_usage("/")
    disk_free_gb = round(disk.free / (1024**3), 2)

    gpu_available = gpu_vendor not in ("cpu", "unknown") and vram_gb is not None

    # Build recommended model list based on VRAM/RAM
    recommended_models: list[str] = []
    warnings: list[str] = []
    recommended_seq = 1024

    effective_mem = vram_gb if gpu_available else cpu_ram_gb * 0.3

    if effective_mem is None or effective_mem < 2:
        warnings.append("Very limited GPU memory — CPU inference only or tiny models.")
        recommended_models = []
        recommended_seq = 512
    elif effective_mem < 4:
        recommended_models = ["Qwen/Qwen2.5-0.5B-Instruct"]
        recommended_seq = 512
        warnings.append("Low VRAM — use 0.5B models with NF4 quantization.")
    elif effective_mem < 6:
        recommended_models = [
            "Qwen/Qwen2.5-0.5B-Instruct",
            "Qwen/Qwen2.5-1.5B-Instruct",
        ]
        recommended_seq = 1024
    elif effective_mem < 10:
        recommended_models = [
            "Qwen/Qwen2.5-1.5B-Instruct",
            "Qwen/Qwen2.5-3B-Instruct",
        ]
        recommended_seq = 2048
    elif effective_mem < 16:
        recommended_models = [
            "Qwen/Qwen2.5-3B-Instruct",
            "Qwen/Qwen2.5-7B-Instruct",
            "meta-llama/Llama-3.2-3B-Instruct",
        ]
        recommended_seq = 2048
    else:
        recommended_models = [
            "Qwen/Qwen2.5-7B-Instruct",
            "meta-llama/Llama-3.1-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ]
        recommended_seq = 4096

    if cpu_ram_gb < 8:
        warnings.append("Low system RAM (< 8 GB) — limit dataset size and batch size.")

    if disk_free_gb < 20:
        warnings.append(f"Low disk space ({disk_free_gb:.1f} GB free) — model weights may not fit.")

    return {
        "gpu_available": gpu_available,
        "gpu_vendor": gpu_vendor,
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "cpu_ram_gb": cpu_ram_gb,
        "disk_free_gb": disk_free_gb,
        "python_version": sys.version.split()[0],
        "torch_version": torch_version,
        "cuda_available": cuda_available,
        "recommended_max_seq_length": recommended_seq,
        "recommended_models": recommended_models,
        "warnings": warnings,
    }
