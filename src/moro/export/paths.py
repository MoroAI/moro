"""Constrain deployment names and paths before creating any artifacts."""

import re
from pathlib import Path

from moro.core.errors import ExportError


def deployment_directory(root: Path, run_id: str, tag: str | None) -> Path:
    version = "latest" if tag is None else tag
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", version):
        raise ExportError(
            "Invalid deployment tag: use 1–128 letters, digits, dots, underscores, "
            "or hyphens, starting with a letter or digit."
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id):
        raise ExportError("Invalid recorded run ID for deployment.")
    root = root.resolve()
    releases = root / "releases"
    output = releases / f"{run_id}_{version}"
    for path in (releases, output, output / "ollama_package"):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ExportError(
                "Deployment destination must stay inside the project without symlinks."
            )
    if not output.resolve().is_relative_to(releases.resolve()):
        raise ExportError("Deployment destination must stay inside releases.")
    return output
