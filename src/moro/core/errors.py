class MoroError(Exception):
    """Base exception for all MoroAI errors."""


class ProjectError(MoroError):
    """Raised when a project is missing, invalid, or not found."""


class ConfigError(MoroError):
    """Raised when moro.yaml is missing or invalid."""


class DatasetError(MoroError):
    """Raised for dataset ingestion, normalization, or splitting problems."""


class DependencyError(MoroError):
    """Raised when an optional dependency is missing."""


class TrainingError(MoroError):
    """Raised when training fails."""


class ExportError(MoroError):
    """Raised when export or deployment fails."""


class EvalError(MoroError):
    """Raised when evaluation fails."""


class RecipeError(MoroError):
    """Raised when recipe suggestion fails."""
