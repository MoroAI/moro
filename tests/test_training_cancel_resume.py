"""Cancellation and checkpoint resume are documented as unimplemented."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "cancel-resume-test-token-" + "b" * 32


@pytest.fixture
def client(tmp_project, monkeypatch):
    from moro.dashboard.mission_control import mission_app

    monkeypatch.chdir(tmp_project)
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    return TestClient(mission_app, base_url="http://127.0.0.1")


@pytest.fixture
def recorded_run(client):
    from moro.storage import db

    conn = db.get_connection(Path.cwd())
    try:
        project = db.get_or_create_project(conn, "test-project", "local_only")
        return db.create_run(conn, project, "config-hash", "local-model", "none", "runs/x")
    finally:
        conn.close()


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.mark.parametrize("action", ["stop", "cancel"])
def test_stop_and_cancel_report_409_without_stopping(client, recorded_run, action):
    from moro.storage import db

    response = client.post(f"/api/training/runs/{recorded_run}/{action}", headers=_auth())
    assert response.status_code == 409
    assert "not implemented" in response.json()["detail"].lower()
    assert "no cancellation was performed" in response.json()["detail"]
    conn = db.get_connection(Path.cwd())
    try:
        row = conn.execute("SELECT status FROM runs WHERE id = ?", (recorded_run,)).fetchone()
        assert row["status"] == "pending"
    finally:
        conn.close()


def test_resume_reports_409_without_starting(client, recorded_run):
    response = client.post(f"/api/training/runs/{recorded_run}/resume", headers=_auth())
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Checkpoint resume is not implemented; no training was started"
    )


@pytest.mark.parametrize("action", ["stop", "cancel", "resume"])
def test_missing_run_is_404_not_409(client, action):
    response = client.post(f"/api/training/runs/missing/{action}", headers=_auth())
    assert response.status_code == 404


def test_operations_resume_job_mirrors_training_api(client, recorded_run):
    missing = client.post(
        "/api/operations/resume_job", json={"job_id": "missing"}, headers=_auth()
    )
    assert missing.status_code == 404
    response = client.post(
        "/api/operations/resume_job", json={"job_id": recorded_run}, headers=_auth()
    )
    assert response.status_code == 409
    assert "no training was started" in response.json()["detail"]


def test_operations_resume_job_rejects_strict_input(client):
    response = client.post(
        "/api/operations/resume_job", json={"job_id": "run;id"}, headers=_auth()
    )
    assert response.status_code == 422


def test_dashboard_template_documents_no_cancel_no_resume(client):
    html = client.get("/", headers=_auth()).text
    assert "Process cancellation and checkpoint resume are not implemented" in html
    assert "runs cannot be resumed" in html
    assert 'value="resume_job"' in html
    assert "Checkpoint resume is not implemented" in html
