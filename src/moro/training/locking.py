"""One training process per project across CLI, SDK and HTTP entry points."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from moro.core.errors import TrainingError


@contextmanager
def training_lock(root: Path):
    directory = Path(root) / ".moro"
    if directory.is_symlink():
        raise TrainingError("Training state directory cannot be a symbolic link")
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(
        directory / "training.execution.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise TrainingError("Another training operation is active in this project") from exc
        yield
    finally:
        os.close(fd)
