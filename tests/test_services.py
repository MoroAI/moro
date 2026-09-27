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
