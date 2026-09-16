"""
Ollama deployment packager.

Generates a folder with:
  - Modelfile (Ollama format)
  - README with deploy instructions
"""

from __future__ import annotations

from pathlib import Path

from moro.core.errors import ExportError


def generate_ollama_package(
    adapter_path: Path,
    base_model: str,
    project_name: str,
    out_dir: Path,
    system_prompt: str | None = None,
) -> Path:
    """
    Generate an Ollama-compatible deployment package.

    The package contains a Modelfile that references the adapter and
    base model for local serving via `ollama create`.

    Returns the path to the generated package directory.
    """
    adapter_path = Path(adapter_path)
    out_dir = Path(out_dir)

    if not adapter_path.exists():
        raise ExportError(f"Adapter path does not exist: {adapter_path}")

    package_dir = out_dir / "ollama_package"
    package_dir.mkdir(parents=True, exist_ok=True)

    # Modelfile content
    system_line = f'\nSYSTEM """{system_prompt}"""' if system_prompt else ""
    modelfile = f"""\
# MoroAI generated Modelfile
# Base model: {base_model}
# Project: {project_name}
#
# Usage:
#   ollama create {project_name.lower().replace(" ", "-")} -f Modelfile
#   ollama run {project_name.lower().replace(" ", "-")}

FROM {base_model}
ADAPTER {adapter_path.resolve()}{system_line}

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
"""

    modelfile_path = package_dir / "Modelfile"
    modelfile_path.write_text(modelfile, encoding="utf-8")

    readme = f"""\
# {project_name} — Ollama Deployment

## Deploy

```bash
ollama create {project_name.lower().replace(" ", "-")} -f Modelfile
```

## Run

```bash
ollama run {project_name.lower().replace(" ", "-")}
```

## Requirements

- [Ollama](https://ollama.ai) installed and running
- Base model `{base_model}` pulled via Ollama (or available locally)

## Files

- `Modelfile` — Ollama model definition referencing adapter at:
  `{adapter_path.resolve()}`
"""

    (package_dir / "README.md").write_text(readme, encoding="utf-8")

    return package_dir
