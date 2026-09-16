from pathlib import Path

MORO_DIR = ".moro"
CONFIG_FILE = "moro.yaml"

PROJECT_DIRS = [
    ".moro",
    ".moro/artifacts",
    ".moro/logs",
    ".moro/reports",
    "data",
    "data/raw",
    "data/normalized",
    "data/splits",
    "eval",
    "runs",
    "releases",
]


def find_project_root(start: Path | None = None) -> Path | None:
    """
    Search upward from start path until a moro.yaml file is found.
    Returns None if no project root is found.
    """
    current = Path(start or Path.cwd()).expanduser().resolve()

    for candidate in [current, *current.parents]:
        if (candidate / CONFIG_FILE).exists():
            return candidate

    return None


def project_dirs(root: Path) -> dict[str, Path]:
    """
    Return canonical project directories as a dictionary.
    """
    return {
        "root": root,
        "moro": root / MORO_DIR,
        "artifacts": root / MORO_DIR / "artifacts",
        "logs": root / MORO_DIR / "logs",
        "reports": root / MORO_DIR / "reports",
        "data": root / "data",
        "raw": root / "data" / "raw",
        "normalized": root / "data" / "normalized",
        "splits": root / "data" / "splits",
        "eval": root / "eval",
        "runs": root / "runs",
        "releases": root / "releases",
    }


def ensure_project_dirs(root: Path) -> dict[str, Path]:
    """
    Create all expected project directories if they do not exist.
    Returns the dirs dict.
    """
    dirs = project_dirs(root)

    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)

    return dirs
