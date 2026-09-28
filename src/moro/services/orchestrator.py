"""
MoroAI Service Orchestrator.

Manages all background services: start, stop, restart, monitor, supervise.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from moro.core.paths import find_project_root
from moro.state.schema import initialize_state_db

console = Console()


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    """Check if a TCP port is currently listening."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


class ServiceDefinition:
    """Definition of a managed background service."""

    def __init__(
        self,
        name: str,
        service_type: str,
        command: list[str],
        port: int | None = None,
        host: str = "127.0.0.1",
        env: dict[str, str] | None = None,
        health_check_url: str | None = None,
        auto_restart: bool = True,
        max_restarts: int = 3,
        description: str = "",
    ) -> None:
        self.name = name
        self.service_type = service_type
        self.command = command
        self.port = port
        self.host = host
        self.env = env or {}
        self.health_check_url = health_check_url
        self.auto_restart = auto_restart
        self.max_restarts = max_restarts
        self.description = description


class ServiceStatusList(list):
    """Dual list/dictionary interface for service statuses."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            for item in self:
                if item.get("name") == key:
                    return item
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, key: Any) -> bool:
        if isinstance(key, str):
            return any(item.get("name") == key for item in self)
        return super().__contains__(key)

    def values(self) -> list[dict[str, Any]]:
        return list(self)

    def keys(self) -> list[str]:
        return [item["name"] for item in self if "name" in item]

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        return [(item["name"], item) for item in self if "name" in item]

    def get(self, key: str, default: Any = None) -> Any:
        for item in self:
            if item.get("name") == key:
                return item
        return default


class ServiceOrchestrator:
    """Orchestrates all MoroAI background services.

    Provides:
    - Start/stop/restart individual services
    - Start/stop all services
    - Health monitoring and state persistence in state.db
    - Log retrieval
    - Process supervision with auto-restart
    """

    def __init__(self, root: Path | None = None, state_db_path: Path | None = None) -> None:
        self.root = root or find_project_root() or Path.cwd()
        self.state_db_path = state_db_path or (self.root / ".moro" / "state.db")
        self.logs_dir = self.root / ".moro" / "logs"
        self.pids_dir = self.root / ".moro" / "pids"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.pids_dir.mkdir(parents=True, exist_ok=True)

        self._processes: dict[str, subprocess.Popen] = {}
        self._restart_counts: dict[str, int] = {}
        self.services = self._define_services()

        # Ensure state db exists for recording service statuses
        try:
            if not self.state_db_path.exists():
                initialize_state_db(self.state_db_path)
        except Exception:
            pass

    def _define_services(self) -> dict[str, ServiceDefinition]:
        """Define all managed background services."""
        venv_bin = self.root / ".venv" / "bin"
        python_exec = str(venv_bin / "python") if (venv_bin / "python").exists() else sys.executable

        return {
            "dashboard": ServiceDefinition(
                name="dashboard",
                service_type="ui",
                command=[
                    python_exec,
                    "-m",
                    "uvicorn",
                    "moro.dashboard.mission_control:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8765",
                ],
                port=8765,
                health_check_url="http://127.0.0.1:8765/api/health",
                auto_restart=True,
                description="Mission Control Web Operations Center",
            ),
            "ollama": ServiceDefinition(
                name="ollama",
                service_type="inference",
                command=["ollama", "serve"],
                port=11434,
                health_check_url="http://127.0.0.1:11434/api/tags",
                auto_restart=True,
                description="Ollama LLM Engine & API",
            ),
            "webhook": ServiceDefinition(
                name="webhook",
                service_type="ingestion",
                command=[
                    python_exec,
                    "-m",
                    "uvicorn",
                    "moro.flywheel.webhook.receiver:webhook_app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8001",
                ],
                port=8001,
                health_check_url="http://127.0.0.1:8001/webhook/stats",
                auto_restart=True,
                description="Production Telemetry & Log Receiver",
            ),
            "gateway": ServiceDefinition(
                name="gateway",
                service_type="proxy",
                command=[
                    python_exec,
                    "-m",
                    "uvicorn",
                    "moro.dashboard.gateway:gateway_app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                port=8000,
                health_check_url="http://127.0.0.1:8000/health",
                auto_restart=True,
                description="Feedback Gateway Proxy",
            ),
        }

    def _read_pid(self, name: str) -> int | None:
        pid_file = self.pids_dir / f"{name}.pid"
        if not pid_file.exists():
            return None
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)
            return None

    def _write_pid(self, name: str, pid: int) -> None:
        (self.pids_dir / f"{name}.pid").write_text(str(pid))

    def _remove_pid(self, name: str) -> None:
        (self.pids_dir / f"{name}.pid").unlink(missing_ok=True)

    def _check_health(self, service: ServiceDefinition) -> bool:
        """Check if a service is healthy."""
        if service.port and not is_port_open(service.port, host=service.host):
            return False

        if not service.health_check_url:
            return True

        try:
            import httpx

            resp = httpx.get(service.health_check_url, timeout=1.5)
            return resp.status_code in (200, 204, 307)
        except Exception:
            return False

    def _register_service_state(
        self,
        service: ServiceDefinition,
        status: str,
        pid: int | None = None,
        health_status: str = "unknown",
    ) -> None:
        """Update service state in the SQLite state database."""
        if not self.state_db_path.exists():
            return
        import sqlite3

        try:
            conn = sqlite3.connect(str(self.state_db_path))
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT OR REPLACE INTO service_state (
                    service_id, service_name, service_type,
                    pid, port, host, status, health_status,
                    started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"svc_{service.name}",
                    service.name,
                    service.service_type,
                    pid,
                    service.port,
                    service.host,
                    status,
                    health_status,
                    now if status == "running" else None,
                    now,
                ),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ===================================================================
    # SERVICE CONTROL OPERATIONS
    # ===================================================================

    def get_status(self) -> ServiceStatusList:
        """Return the running status of all managed services."""
        items: list[dict[str, Any]] = []
        for name, service in self.services.items():
            running = is_port_open(service.port) if service.port else False
            pid = self._read_pid(name)
            healthy = self._check_health(service) if running else False

            service_type = "docker" if name == "ollama" and not pid else service.service_type
            items.append(
                {
                    "name": name,
                    "type": service_type,
                    "port": service.port,
                    "url": f"http://localhost:{service.port}" if service.port else "",
                    "running": running,
                    "healthy": healthy,
                    "pid": pid,
                    "description": service.description,
                }
            )
        return ServiceStatusList(items)

    def start_service(self, name: str) -> bool:
        """Start a specific service."""
        name = name.lower()
        if name not in self.services:
            console.print(f"[red]Unknown service: {name}[/red]")
            return False

        service = self.services[name]

        # Check if already running on designated port
        if service.port and is_port_open(service.port):
            self._register_service_state(
                service, "running", pid=self._read_pid(name), health_status="healthy"
            )
            return True

        # Special handling for Ollama (supports Docker container)
        if name == "ollama":
            try:
                subprocess.run(
                    ["docker", "start", "moro-ollama"],
                    capture_output=True,
                    timeout=8,
                )
                time.sleep(1)
                if is_port_open(11434):
                    self._register_service_state(service, "running", health_status="healthy")
                    return True
            except Exception:
                pass

        # Launch via subprocess
        try:
            log_file = open(self.logs_dir / f"{name}.log", "a")
            env = os.environ.copy()
            env.update(service.env)

            proc = subprocess.Popen(
                service.command,
                cwd=str(self.root),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )

            self._processes[name] = proc
            self._restart_counts[name] = 0
            self._write_pid(name, proc.pid)

            # Wait briefly and verify startup
            time.sleep(1.5)
            running = (service.port and is_port_open(service.port)) or (proc.poll() is None)
            health = "healthy" if self._check_health(service) else "starting"
            self._register_service_state(
                service, "running" if running else "failed", pid=proc.pid, health_status=health
            )
            return running
        except Exception as e:
            console.print(f"[red]Failed to start {name}: {e}[/red]")
            self._register_service_state(service, "failed", health_status="unhealthy")
            return False

    def stop_service(self, name: str) -> bool:
        """Stop a specific service."""
        name = name.lower()
        if name not in self.services:
            return False

        service = self.services[name]

        if name == "ollama":
            try:
                subprocess.run(["docker", "stop", "moro-ollama"], capture_output=True, timeout=8)
            except Exception:
                pass

        # Stop tracked process
        if name in self._processes:
            proc = self._processes[name]
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            del self._processes[name]

        # Stop via PID file if present
        pid = self._read_pid(name)
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            self._remove_pid(name)

        self._register_service_state(service, "stopped", health_status="offline")
        return True

    def restart_service(self, name: str) -> bool:
        """Restart a specific service."""
        console.print(f"[cyan]Restarting {name}...[/cyan]")
        self.stop_service(name)
        time.sleep(1)
        return self.start_service(name)

    def start_all(self) -> dict[str, bool]:
        """Start all configured services."""
        results: dict[str, bool] = {}
        for service_name in ["dashboard", "ollama", "webhook"]:
            results[service_name] = self.start_service(service_name)
        return results

    def stop_all(self) -> dict[str, bool]:
        """Stop all configured services."""
        results: dict[str, bool] = {}
        for service_name in ["dashboard", "ollama", "webhook", "gateway"]:
            results[service_name] = self.stop_service(service_name)
        return results

    def print_status(self) -> None:
        """Print a formatted status table to the console."""
        statuses = self.get_status()

        table = Table(title="MoroAI Service Status", show_header=True)
        table.add_column("Service", style="cyan bold")
        table.add_column("Type", style="white")
        table.add_column("Port", justify="right", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Health", style="white")
        table.add_column("PID", justify="right", style="dim")

        for s in statuses.values():
            status_str = "[green]Running[/green]" if s["running"] else "[red]Stopped[/red]"
            health_str = "[green]Healthy[/green]" if s["healthy"] else "[yellow]Unknown[/yellow]"
            if s["running"] and not s["healthy"]:
                health_str = "[red]Unhealthy[/red]"

            table.add_row(
                s["name"],
                str(s["type"]),
                str(s["port"] or "-"),
                status_str,
                health_str,
                str(s["pid"] or "-"),
            )

        console.print(table)

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

    def get_service_logs(self, name: str, tail: int = 50) -> str:
        """Alias for get_logs."""
        return self.get_logs(name, tail=tail)

    def supervise(self) -> None:
        """Main supervision loop that monitors and auto-restarts services if they crash."""
        console.print(
            "[cyan]Starting service supervisor loop (Press Ctrl+C to terminate)...[/cyan]"
        )
        try:
            while True:
                for service_name, proc in list(self._processes.items()):
                    if proc.poll() is not None:
                        service = self.services[service_name]
                        if service.auto_restart:
                            count = self._restart_counts.get(service_name, 0)
                            if count < service.max_restarts:
                                console.print(
                                    f"[yellow]Service '{service_name}' exited. "
                                    f"Auto-restarting ({count + 1}/{service.max_restarts})...[/yellow]"
                                )
                                self._restart_counts[service_name] = count + 1
                                self.start_service(service_name)
                            else:
                                console.print(
                                    f"[red]Service '{service_name}' exceeded maximum restart attempts.[/red]"
                                )
                                self._register_service_state(
                                    service, "failed", health_status="crashed"
                                )
                                del self._processes[service_name]
                time.sleep(4)
        except KeyboardInterrupt:
            console.print("\n[yellow]Supervisor stopped.[/yellow]")
            self.stop_all()
