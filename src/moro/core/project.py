from pathlib import Path

from moro.config.loader import load_config
from moro.config.models import MoroConfig
from moro.core.errors import ProjectError
from moro.core.paths import CONFIG_FILE, find_project_root


def require_project_root(start: Path | None = None) -> Path:
    """
    Return the project root path or raise ProjectError if not inside a project.
    """
    root = find_project_root(start)

    if root is None:
        raise ProjectError(
            "Not inside a MoroAI project. "
            "Run `moro init` to create one, or `cd` into an existing project."
        )

    return root


def load_project_config(start: Path | None = None) -> MoroConfig:
    """
    Load and return the validated moro.yaml from the current project.
    Raises ProjectError or ConfigError on failure.
    """
    root = require_project_root(start)
    return load_config(root / CONFIG_FILE)
