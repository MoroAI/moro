"""
MoroAI Service Orchestrator.

Manages background services:
- dashboard: Mission Control Web Interface (:8765)
- ollama: Local inference daemon in Docker (:11434)
- webhook: DPO production telemetry receiver (:8000)
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from moro.core.paths import find_project_root


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


class ServiceOrchestrator:
    """Manages starting, stopping, and inspecting MoroAI background services."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or find_project_root() or Path.cwd()
        self.logs_dir = self.root / ".moro" / "logs"
        self.pids_dir = self.root / ".moro" / "pids"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pids_dir.mkdir(parents=True, exist_ok=True)

    def _read_pid(self, name: str) -> int | None:
        pid_file = self.pids_dir / f"{name}.pid"
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            # Check if process is still alive
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
            return None

    def _write_pid(self, name: str, pid: int) -> None:
        (self.pids_dir / f"{name}.pid").write_text(str(pid))

    def _remove_pid(self, name: str) -> None:
        (self.pids_dir / f"{name}.pid").unlink(missing_ok=True)

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Return the running status of all managed services."""
        return {
            "dashboard": {
                "port": 8765,
                "url": "http://localhost:8765",
                "running": is_port_open(8765),
                "pid": self._read_pid("dashboard"),
                "description": "Mission Control Web Operations Center",
            },
            "ollama": {
                "port": 11434,
                "url": "http://localhost:11434",
                "running": is_port_open(11434),
                "type": "docker",
                "description": "Ollama LLM Engine & API",
            },
            "webhook": {
                "port": 8001,
                "url": "http://localhost:8001",
                "running": is_port_open(8001),
                "pid": self._read_pid("webhook"),
                "description": "Production Telemetry & Log Receiver",
            },
        }

    def start_service(self, name: str) -> bool:
        """Start a specific service."""
        name = name.lower()
        if name == "dashboard":
            if is_port_open(8765):
                return True
            log_file = open(self.logs_dir / "dashboard.log", "a")
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "moro.dashboard.mission_control:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                ],
                cwd=str(self.root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._write_pid("dashboard", proc.pid)
            return True

        if name == "ollama":
            if is_port_open(11434):
                return True
            try:
                subprocess.run(
                    ["docker", "start", "moro-ollama"],
                    capture_output=True,
                    timeout=10,
                )
                return is_port_open(11434)
            except Exception:
                return False

        if name == "webhook":
            if is_port_open(8001):
                return True
            log_file = open(self.logs_dir / "webhook.log", "a")
            venv_moro = self.root / ".venv" / "bin" / "moro"
            cmd = [str(venv_moro) if venv_moro.exists() else "moro", "flywheel", "serve"]
            proc = subprocess.Popen(
                cmd,
                cwd=str(self.root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            self._write_pid("webhook", proc.pid)
            return True

        return False

    def stop_service(self, name: str) -> bool:
        """Stop a specific service."""
        name = name.lower()
        if name in ("dashboard", "webhook"):
            pid = self._read_pid(name)
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                except OSError:
                    pass
                self._remove_pid(name)
                return True
            return False

        if name == "ollama":
            try:
                subprocess.run(
                    ["docker", "stop", "moro-ollama"],
                    capture_output=True,
                    timeout=10,
                )
                return True
            except Exception:
                return False

        return False

    def get_logs(self, name: str, tail: int = 50) -> str:
        """Retrieve recent logs for a managed service."""
        name = name.lower()
        if name == "ollama":
            try:
                res = subprocess.run(
                    ["docker", "logs", "--tail", str(tail), "moro-ollama"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                return res.stdout + res.stderr
            except Exception as e:
                return f"Error reading docker logs: {e}"

        log_path = self.logs_dir / f"{name}.log"
        if not log_path.exists():
            return f"No log file found for service '{name}'."

        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            return "\n".join(lines[-tail:])
        except Exception as e:
            return f"Error reading log file: {e}"
