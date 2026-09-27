"""Stage a portable adapter package; the compatible base model is an explicit dependency."""

import json
import tempfile
from pathlib import Path

from moro.core.errors import ExportError
from moro.core.hashing import sha256_directory, sha256_file
from moro.export.manifest import export_adapter


def generate_ollama_package(
    adapter_path: Path,
    base_model: str,
    project_name: str,
    out_dir: Path,
    system_prompt: str | None = None,
) -> Path:
    adapter_path, out_dir = Path(adapter_path), Path(out_dir)
    if any(c in base_model + project_name for c in "\n\r"):
        raise ExportError("Model and project names must not contain line breaks.")
    if system_prompt and ('"""' in system_prompt or "\r" in system_prompt):
        raise ExportError("Unsupported quoting in system prompt.")
    destination = out_dir / "ollama_package"
    if destination.exists() or destination.is_symlink():
        raise ExportError(f"Package destination already exists: {destination}")
    if out_dir.resolve().is_relative_to(adapter_path.resolve()):
        raise ExportError("Deployment output overlaps the source adapter.")
    try:
        before = sha256_directory(adapter_path)
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".ollama-", dir=out_dir) as temporary:
            package = Path(temporary) / "package"
            copied = export_adapter(adapter_path.parent, package)
            if sha256_directory(copied) != before:
                raise ExportError("Adapter changed during packaging.")
            system = f'\nSYSTEM """{system_prompt}"""' if system_prompt else ""
            (package / "Modelfile").write_text(
                f"# MoroAI package; validate base model compatibility before import.\n"
                f"FROM {base_model}\nADAPTER ./adapter{system}\n"
                "PARAMETER temperature 0\nPARAMETER num_predict 256\n",
                encoding="utf-8",
            )
            (package / "README.md").write_text(
                f"# {project_name}: local deployment preparation\n\n"
                "This directory includes an independent adapter copy. The base model is an "
                f"external dependency: `{base_model}`. A Hugging Face ID is not automatically "
                "an Ollama model tag. Resolve a compatible base model using the target runtime's "
                "import instructions before use. Adapter support depends on the runtime version "
                "and architecture; package generation is not a successful serving test.\n\n"
                "From this directory, after validating the Modelfile:\n\n"
                "```sh\nollama create moro-local -f Modelfile\nollama run moro-local\n```\n",
                encoding="utf-8",
            )
            manifest = {
                "schema_version": 1,
                "base_model": base_model,
                "base_model_included": False,
                "adapter_sha256": before,
                "files": {
                    p.relative_to(package).as_posix(): sha256_file(p)
                    for p in package.rglob("*")
                    if p.is_file()
                },
            }
            (package / "package_manifest.json").write_text(json.dumps(manifest, indent=2))
            if destination.exists() or destination.is_symlink():
                raise ExportError("Package destination appeared during export.")
            package.rename(destination)
        return destination
    except (OSError, ValueError) as exc:
        raise ExportError(f"Cannot prepare Ollama package: {exc}") from exc
