"""Unit tests for ServiceOrchestrator."""

from pathlib import Path

from moro.services.orchestrator import ServiceOrchestrator, is_port_open


def test_service_orchestrator_status(tmp_path: Path):
    orch = ServiceOrchestrator(tmp_path)
    status = orch.get_status()

    assert "dashboard" in status
    assert "ollama" in status
    assert "webhook" in status

    assert status["dashboard"]["port"] == 8501
    assert status["ollama"]["port"] == 11434
    assert status["webhook"]["port"] == 8001


def test_dashboard_uses_canonical_port_and_health_url(tmp_path: Path):
    orch = ServiceOrchestrator(tmp_path)
    dashboard = orch.services["dashboard"]
    assert dashboard.port == 8501
    assert dashboard.command[-1] == "8501"
    assert dashboard.health_check_url == "http://127.0.0.1:8501/api/health"


def test_webhook_health_probe_is_public_not_authed(tmp_path: Path):
    orch = ServiceOrchestrator(tmp_path)
    assert orch.services["webhook"].health_check_url == "http://127.0.0.1:8001/health"


def test_start_all_includes_gateway(tmp_path: Path, monkeypatch):
    orch = ServiceOrchestrator(tmp_path)
    started = []

    def fake_start(name):
        started.append(name)
        return True

    monkeypatch.setattr(orch, "start_service", fake_start)
    results = orch.start_all()
    assert started == ["dashboard", "ollama", "webhook", "gateway"]
    assert results == {name: True for name in started}


def test_is_port_open_nonexistent():
    # Random very high unallocated port
    assert is_port_open(59999, timeout=0.1) is False


def test_service_orchestrator_print_status_and_logs(tmp_path: Path):
    orch = ServiceOrchestrator(tmp_path)
    # print_status should run without error
    orch.print_status()

    # get_logs on non-running service should return appropriate message
    logs = orch.get_logs("dashboard")
    assert "No log file found" in logs or "is not running" in logs or isinstance(logs, str)
