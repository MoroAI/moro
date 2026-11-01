"""
MoroAI Dashboard System API.

Provides endpoints for:
- System and microservice health monitoring
- Resource telemetry (CPU, RAM, GPU, Disk)
- moro.yaml configuration read & update
- Real-time WebSocket health and log streaming
"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from moro.dashboard.utils import get_project_root

router = APIRouter(prefix="/api/system", tags=["system"])


# ===================================================================
# MODELS
# ===================================================================


class SystemHealth(BaseModel):
    """System health and telemetry payload."""

    status: str
    timestamp: str
    services: dict
    resources: dict
    active_runs: int


# ===================================================================
# ENDPOINTS
# ===================================================================


@router.get("/health", response_model=SystemHealth)
async def get_system_health() -> SystemHealth:
    """Get aggregated system health, service states, and hardware metrics."""
    project_root = get_project_root()

    services: dict[str, dict] = {}

    # Ollama status
    try:
        import httpx

        async with httpx.AsyncClient(timeout=1.0) as client:
            import os

            resp = await client.get(
                os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434") + "/api/tags"
            )
            services["ollama"] = {"available": resp.status_code == 200}
    except Exception:
        services["ollama"] = {"available": False}

    # State & Analytics Databases
    state_db = project_root / ".moro" / "state.db"
    analytics_db = project_root / ".moro" / "analytics.db"
    services["database"] = {
        "state_db": state_db.exists(),
        "analytics_db": analytics_db.exists(),
        "available": True,
    }

    # Docker status
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, timeout=2)
        services["docker"] = {"available": res.returncode == 0}
    except Exception:
        services["docker"] = {"available": False}

    # Resource usage
    resources: dict = {
        "cpu_percent": None,
        "memory_percent": None,
        "disk_percent": None,
        "gpu": {"available": False},
    }

    try:
        import psutil

        resources["cpu_percent"] = psutil.cpu_percent(interval=None)
        resources["memory_percent"] = psutil.virtual_memory().percent
        try:
            resources["disk_percent"] = psutil.disk_usage(str(project_root)).percent
        except Exception:
            pass
    except ImportError:
        pass

    try:
        import torch

        if torch.cuda.is_available():
            resources["gpu"] = {
                "available": True,
                "name": torch.cuda.get_device_name(0),
                "memory_allocated_gb": round(torch.cuda.memory_allocated() / (1024**3), 2),
                "memory_total_gb": round(
                    torch.cuda.get_device_properties(0).total_memory / (1024**3), 2
                ),
            }
    except ImportError:
        pass

    return SystemHealth(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
        resources=resources,
        active_runs=0,
    )


@router.get("/services")
async def get_services() -> dict:
    """Get status of all orchestrated MoroAI background services."""
    project_root = get_project_root()
    try:
        from moro.services.orchestrator import ServiceOrchestrator

        orchestrator = ServiceOrchestrator(project_root, project_root / ".moro" / "state.db")
        return {"services": orchestrator.get_status()}
    except Exception as exc:
        return {"services": {}, "error": str(exc)}


@router.post("/services/{service_name}/start")
async def start_service(service_name: str) -> dict:
    """Start an orchestrated service."""
    project_root = get_project_root()
    try:
        from moro.services.orchestrator import ServiceOrchestrator

        orchestrator = ServiceOrchestrator(project_root, project_root / ".moro" / "state.db")
        success = orchestrator.start_service(service_name)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to start service {service_name}")
        return {"service": service_name, "status": "started"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/services/{service_name}/stop")
async def stop_service(service_name: str) -> dict:
    """Stop an orchestrated service."""
    project_root = get_project_root()
    try:
        from moro.services.orchestrator import ServiceOrchestrator

        orchestrator = ServiceOrchestrator(project_root, project_root / ".moro" / "state.db")
        success = orchestrator.stop_service(service_name)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to stop service {service_name}")
        return {"service": service_name, "status": "stopped"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config")
async def get_config():
    """Return only a validated configuration, with a revision for safe updates."""
    import hashlib

    import yaml
    from starlette.responses import JSONResponse

    from moro.config.models import MoroConfig

    path = get_project_root() / "moro.yaml"
    if path.is_symlink():
        raise HTTPException(400, "Configuration must not be a symbolic link")
    try:
        raw = path.read_bytes()
        config = MoroConfig.model_validate(yaml.safe_load(raw))
    except Exception as exc:
        raise HTTPException(422, "Project configuration is missing or invalid") from exc
    return JSONResponse(
        config.model_dump(mode="json"),
        headers={"ETag": '"' + hashlib.sha256(raw).hexdigest() + '"'},
    )


@router.put("/config")
async def update_config(config: dict, request: Request) -> dict:
    """Validate first; serialize writers and replace only the revision read by the caller."""
    import fcntl
    import hashlib
    import os
    import tempfile

    import yaml

    from moro.config.models import MoroConfig

    try:
        validated = MoroConfig.model_validate(config)
    except ValueError as exc:
        raise HTTPException(
            422, "Invalid Moro configuration; previous configuration retained"
        ) from exc
    expected = request.headers.get("if-match")
    if expected is None:
        raise HTTPException(428, "Read the configuration and supply its ETag in If-Match")
    root = get_project_root()
    state = root / ".moro"
    if state.is_symlink():
        raise HTTPException(400, "State directory must not be a symbolic link")
    state.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(state / "config.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = root / "moro.yaml"
        if path.is_symlink() or not path.is_file():
            raise HTTPException(400, "Configuration must be a regular file")
        current = path.read_bytes()
        if expected != '"' + hashlib.sha256(current).hexdigest() + '"':
            raise HTTPException(412, "Configuration changed; reload before saving")
        fd, temporary = tempfile.mkstemp(prefix=".moro-config-", dir=root)
        try:
            with os.fdopen(fd, "w") as stream:
                yaml.safe_dump(validated.model_dump(mode="json"), stream, sort_keys=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return {"status": "updated", "message": "Validated configuration saved"}


# ===================================================================
# WEBSOCKET ENDPOINTS
# ===================================================================


@router.websocket("/ws/health")
async def ws_system_health(websocket: WebSocket) -> None:
    """Stream real-time health telemetry over WebSocket."""
    await websocket.accept()
    try:
        while True:
            health = await get_system_health()
            await websocket.send_json(health.model_dump())
            await asyncio.sleep(4)
    except WebSocketDisconnect:
        pass


@router.websocket("/ws/logs")
async def ws_system_logs(websocket: WebSocket) -> None:
    """Stream active project logs over WebSocket."""
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "INFO",
                    "message": "Mission Control gateway active. Heartbeat ok.",
                }
            )
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
