"""SDK adapter for the same versioned compiler used by the CLI."""

from pathlib import Path
from typing import Any

from moro.config.loader import load_config
from moro.config.models import DatasetConfig
from moro.core.errors import DatasetError


class DataCompiler:
    def __init__(self, project_root: Path, state_manager: Any = None):
        self.project_root = Path(project_root).resolve()
        self.state_manager = state_manager

    def compile_dataset(self, source_path: Path | str, config: dict[str, Any] | None = None) -> str:
        from moro.cli.data import compile_project

        source = Path(source_path)
        if not source.is_absolute():
            source = self.project_root / source
        if not source.exists():
            raise DatasetError("Dataset source does not exist")
        source = source.resolve()
        if source.is_relative_to(self.project_root):
            source = source.relative_to(self.project_root)
        cfg = load_config(self.project_root / "moro.yaml")
        cfg.dataset = DatasetConfig.model_validate(
            {**cfg.dataset.model_dump(), **(config or {}), "source": source}
        )
        return compile_project(self.project_root, cfg)
