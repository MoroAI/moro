from pathlib import Path

from moro.core.errors import ConfigError, DependencyError


def resolve_model_reference(
    reference: str, *, local_only: bool = True, revision: str | None = None
) -> str:
    """Resolve cached Hub IDs to disk before model libraries can follow references."""
    path = Path(reference).expanduser()
    if path.is_dir():
        return str(path.resolve())
    if path.is_absolute() or reference.startswith(("./", "../", "~")):
        raise ConfigError(f"Local model directory does not exist: {reference}")
    if not local_only:
        return reference
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise DependencyError("Install moroai[train] to resolve cached models.") from exc
    try:
        return snapshot_download(reference, revision=revision, local_files_only=True)
    except Exception as exc:
        raise ConfigError(
            f"Model {reference!r} is not available in the local cache. "
            "Use a local model directory or download the requested revision explicitly first. "
            "Set project.privacy_mode to allow_external only when downloads are intended."
        ) from exc


def model_load_options(*, local_only: bool, trust_remote_code: bool = False) -> dict:
    if local_only and trust_remote_code:
        raise ConfigError("local_only mode does not permit trust_remote_code=true.")
    return {"local_files_only": local_only, "trust_remote_code": trust_remote_code}
