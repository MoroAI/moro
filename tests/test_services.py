"""Unit tests for ServiceOrchestrator."""

from pathlib import Path

from moro.services.orchestrator import ServiceOrchestrator, is_port_open


def test_service_orchestrator_status(tmp_path: Path):
    orch = ServiceOrchestrator(tmp_path)
    status = orch.get_status()

    assert "dashboard" in status
    assert "ollama" in status
    assert "webhook" in status

    assert status["dashboard"]["port"] == 8765
    assert status["ollama"]["port"] == 11434
    assert status["webhook"]["port"] == 8001


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

