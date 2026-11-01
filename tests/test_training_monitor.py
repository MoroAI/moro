"""TrainingMonitor reads the real runs table and fcntl execution lock."""

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from moro.dashboard.mission_control import TrainingMonitor
from moro.storage import db


def _record_run(root: Path, status: str) -> str:
    conn = db.get_connection(root)
    try:
        project = db.get_or_create_project(conn, "monitor-project", "local_only")
        run_id = db.create_run(conn, project, "hash", "local-model", "none", "runs/fixture")
        db.update_run_status(conn, run_id, status)
        return run_id
    finally:
        conn.close()


@contextmanager
def _held_execution_lock(root: Path):
    path = root / ".moro" / "training.execution.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_no_runs_and_no_lock_reports_idle(tmp_path: Path):
    assert TrainingMonitor(tmp_path).get_active_training() is None


def test_stale_lock_file_without_holder_reports_idle(tmp_path: Path):
    lock = tmp_path / ".moro" / "training.execution.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_bytes(b"")
    assert TrainingMonitor(tmp_path).get_active_training() is None


def test_finished_runs_are_not_reported_active(tmp_path: Path):
    _record_run(tmp_path, "completed")
    assert TrainingMonitor(tmp_path).get_active_training() is None


def test_running_run_is_reported_with_details(tmp_path: Path):
    run_id = _record_run(tmp_path, "running")
    active = TrainingMonitor(tmp_path).get_active_training()
    assert active is not None
    assert active["run_id"] == run_id
    assert active["status"] == "running"
    assert active["lock_held"] is False


def test_lock_held_without_recorded_run_is_reported_honestly(tmp_path: Path):
    with _held_execution_lock(tmp_path):
        active = TrainingMonitor(tmp_path).get_active_training()
    assert active is not None
    assert active["status"] == "running"
    assert active["run_id"] is None
    assert active["lock_held"] is True


def test_lock_held_with_recorded_run_reports_both(tmp_path: Path):
    run_id = _record_run(tmp_path, "running")
    with _held_execution_lock(tmp_path):
        active = TrainingMonitor(tmp_path).get_active_training()
    assert active is not None
    assert active["run_id"] == run_id
    assert active["lock_held"] is True
