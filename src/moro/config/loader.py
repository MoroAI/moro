from pathlib import Path

import yaml
from pydantic import ValidationError

from moro.config.models import MoroConfig
from moro.core.errors import ConfigError


def load_config(path: Path) -> MoroConfig:
    """
    Load and validate moro.yaml from *path*.

    Raises:
        ConfigError: if the file is missing, unreadable, invalid YAML, or fails schema validation.
    """
    path = Path(path).expanduser().resolve()

    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read config file: {path}") from exc

    try:
        data = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file: {path}\n{exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Top-level YAML must be a mapping, got: {type(data).__name__}")

    try:
        return MoroConfig.model_validate(data)
    except ValidationError as exc:
        # Format Pydantic errors into human-readable lines
        lines = []
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"])
            lines.append(f"  [{loc}] {err['msg']}")
        detail = "\n".join(lines)
        raise ConfigError(f"Invalid MoroAI config ({path}):\n{detail}") from exc
