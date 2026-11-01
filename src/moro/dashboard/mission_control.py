"""
MoroAI Mission Control Dashboard Backend.

A FastAPI application that provides real-time monitoring and control
of all MoroAI services: Docker, Ollama, SQLite, Training, Flywheel.
"""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from moro.analytics.tracker import ExperimentTracker
from moro.analytics.visualizations import VisualAnalyticsEngine
from moro.core.project import find_project_root
from moro.dashboard.api.datasets import router as datasets_router
from moro.dashboard.api.deployment import router as deployment_router
from moro.dashboard.api.evaluation import router as evaluation_router
from moro.dashboard.api.flywheel import router as flywheel_router
from moro.dashboard.api.models import router as models_router
from moro.dashboard.api.system import router as system_router
from moro.dashboard.api.training import router as training_router
from moro.dashboard.operations import router as operations_router
from moro.dashboard.security import csp_nonce, install_security

CONTAINER_LOGS_DEFAULT_TAIL = 100
CONTAINER_LOGS_MAX_TAIL = 1000

# ===================================================================
# SERVICE CONNECTORS
# ===================================================================


class DockerConnector:
    """Connects to Docker daemon for container management."""

    def __init__(self) -> None:
        self._available: bool | None = None
        self._last_checked: float = 0.0

    @property
    def available(self) -> bool:
        import time

        now = time.time()
        if self._available is not None and (now - self._last_checked) < 5.0:
            return self._available
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=4,
            )
            self._available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._available = False
        self._last_checked = now
        return self._available

    def list_containers(self) -> list[dict]:
        """List all Docker containers."""
        if not self.available:
            return []
        try:
            result = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    "label=moro.managed=true",
                    "--format",
                    "{{json .}}",
                ],
                capture_output=True,
                text=True,
                timeout=6,
            )
            containers = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        containers.append(json.loads(line))
                    except Exception:
                        pass
            return containers
        except Exception:
            return []

    def _is_managed(self, container_id: str) -> bool:
        import re

        if not re.fullmatch(r"[a-f0-9]{12,64}", container_id):
            return False
        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{{index .Config.Labels "moro.managed"}}',
                    container_id,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (OSError, subprocess.TimeoutExpired):
            return False

    def start_container(self, container_id: str) -> bool:
        """Start an explicitly Moro-managed Docker container."""
        if not self._is_managed(container_id):
            return False
        try:
            result = subprocess.run(
                ["docker", "start", container_id],
                capture_output=True,
                timeout=15,
            )
            return result.returncode == 0
        except Exception:
            return False

    def stop_container(self, container_id: str) -> bool:
        """Stop an explicitly Moro-managed Docker container."""
        if not self._is_managed(container_id):
            return False
        try:
            result = subprocess.run(
                ["docker", "stop", container_id],
                capture_output=True,
                timeout=15,
            )
            return result.returncode == 0
        except Exception:
            return False

    def get_container_logs(self, container_id: str, tail: int = CONTAINER_LOGS_DEFAULT_TAIL) -> str:
        """Get container logs, clamped to the supported tail window."""
        try:
            tail = int(tail)
        except (TypeError, ValueError):
            tail = CONTAINER_LOGS_DEFAULT_TAIL
        tail = max(1, min(tail, CONTAINER_LOGS_MAX_TAIL))
        if not self._is_managed(container_id):
            return "Container is not managed by Moro"
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True,
                text=True,
                timeout=8,
            )
            return result.stdout + result.stderr
        except Exception:
            return "Failed to fetch logs"


class OllamaConnector:
    """Connects to Ollama daemon for model management."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        import os

        self.base_url = os.environ.get("OLLAMA_BASE_URL", base_url)
        self._available: bool | None = None
        self._last_checked: float = 0.0

    @property
    def available(self) -> bool:
        import time

        now = time.time()
        if self._available is not None and (now - self._last_checked) < 5.0:
            return self._available
        try:
            import httpx

            response = httpx.get(f"{self.base_url}/api/tags", timeout=1.0)
            self._available = response.status_code == 200
        except Exception:
            self._available = False
        self._last_checked = now
        return self._available

    def list_models(self) -> list[dict]:
        """List all Ollama models."""
        try:
            import httpx

            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.json().get("models", [])
        except Exception:
            return []

    def get_model_info(self, model_name: str) -> dict:
        """Get detailed information about a model."""
        try:
            import httpx

            response = httpx.post(
                f"{self.base_url}/api/show",
                json={"name": model_name},
                timeout=6.0,
            )
            return response.json()
        except Exception:
            return {}

    def generate(self, model_name: str, prompt: str) -> str:
        """Generate a completion from a model."""
        try:
            import httpx

            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False},
                timeout=60.0,
            )
            return response.json().get("response", "")
        except Exception:
            return "Error: Failed to generate response from Ollama"


class DatabaseConnector:
    """Connects to SQLite databases for state management."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.production_db = project_root / "data" / "production_logs.db"
        self.moro_db = project_root / ".moro" / "db.sqlite"

    def get_production_stats(self) -> dict:
        """Get production log statistics."""
        if not self.production_db.exists():
            return {"total_logs": 0, "pending_logs": 0, "processed_logs": 0}

        conn = sqlite3.connect(self.production_db)
        try:
            total = conn.execute("SELECT COUNT(*) FROM inference_logs").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM inference_logs WHERE is_processed = 0"
            ).fetchone()[0]
            return {
                "total_logs": total,
                "pending_logs": pending,
                "processed_logs": total - pending,
            }
        except Exception:
            return {"total_logs": 0, "pending_logs": 0, "processed_logs": 0}
        finally:
            conn.close()

    def get_recent_logs(self, limit: int = 20) -> list[dict]:
        """Get recent production logs."""
        if not self.production_db.exists():
            return []

        conn = sqlite3.connect(self.production_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM inference_logs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_training_runs(self) -> list[dict]:
        """Get training run history."""
        from moro.storage import db

        conn = db.get_connection(self.project_root)
        try:
            return [
                {
                    **dict(row),
                    "run_id": row["id"],
                    "name": row["run_name"] or row["model_name"],
                    "val_loss": row["validation_loss"],
                }
                for row in conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 20")
            ]
        finally:
            conn.close()

    def get_registered_models(self) -> list[dict]:
        """Get models from the model registry."""
        registry_db = self.project_root / ".moro" / "state.db"
        if not registry_db.exists():
            return []
        conn = sqlite3.connect(registry_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM model_registry ORDER BY trained_at DESC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()

    def get_state_lineage(self) -> list[dict]:
        """Get nodes from the state graph lineage database."""
        sg_db = self.project_root / ".moro" / "state.db"
        if not sg_db.exists():
            return []
        conn = sqlite3.connect(sg_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM nodes ORDER BY created_at ASC").fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []
        finally:
            conn.close()


def _training_lock_held(project_root: Path) -> bool:
    """Check whether a training process currently holds the fcntl execution lock."""
    import fcntl
    import os

    lock_path = Path(project_root) / ".moro" / "training.execution.lock"
    if not lock_path.exists():
        return False
    try:
        fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    except OSError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


class TrainingMonitor:
    """Monitors active training processes."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def get_active_training(self) -> dict | None:
        """Return the latest run still marked running, with live lock state.

        The runs table identifies which run is active; the fcntl execution
        lock proves a training process holds the project. Either may briefly
        lag the other, so both are reported and neither is fabricated.
        """
        from moro.storage import db

        active: dict | None = None
        try:
            conn = db.get_connection(self.project_root)
            try:
                row = conn.execute(
                    "SELECT * FROM runs WHERE status = 'running' ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row is not None:
                    active = {
                        **dict(row),
                        "run_id": row["id"],
                        "name": row["run_name"] or row["model_name"],
                    }
            finally:
                conn.close()
        except Exception:
            active = None
        lock_held = _training_lock_held(self.project_root)
        if active is None:
            if not lock_held:
                return None
            return {
                "status": "running",
                "run_id": None,
                "lock_held": True,
                "detail": "Training lock is held but no run is marked running.",
            }
        active["lock_held"] = lock_held
        return active

    def get_telemetry(self, run_id: str) -> list[dict]:
        """Get telemetry data for a training run."""
        telemetry_file = self.project_root / "runs" / run_id / "telemetry_report.json"
        if telemetry_file.exists():
            try:
                with open(telemetry_file) as f:
                    data = json.load(f)
                    return data.get("tracker", {}).get("history", [])
            except Exception:
                pass
        return []


class FlywheelMonitor:
    """Monitors the DPO flywheel status."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def get_status(self) -> dict:
        """Get flywheel status."""
        from moro.flywheel.storage.schema import get_production_db

        conn = get_production_db(self.project_root / "data" / "production_logs.db")
        try:
            count = conn.execute("SELECT COUNT(*) FROM dpo_epochs").fetchone()[0]
            pairs = conn.execute("SELECT COUNT(*) FROM preference_pairs").fetchone()[0]
            last = conn.execute(
                "SELECT epoch_id FROM dpo_epochs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            return {
                "active": False,
                "epochs": count,
                "pairs_generated": pairs,
                "last_epoch": last[0] if last else None,
            }
        finally:
            conn.close()


# ===================================================================
# FASTAPI APPLICATION
# ===================================================================

app = FastAPI(
    title="MoroAI Mission Control",
    description="Real-time monitoring and control center for MoroAI Local Model Adaptation Foundry",
    version="1.0.0",
)

install_security(app, browser_login=True)

app.include_router(datasets_router)
app.include_router(training_router)
app.include_router(models_router)
app.include_router(deployment_router)
app.include_router(system_router)
app.include_router(evaluation_router)
app.include_router(flywheel_router)
app.include_router(operations_router)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_connectors: dict[str, object] = {}


def get_project_root() -> Path:
    found = find_project_root()
    return found if found else Path.cwd()


@app.on_event("startup")
async def startup() -> None:
    root = get_project_root()
    _connectors["docker"] = DockerConnector()
    _connectors["ollama"] = OllamaConnector()
    _connectors["database"] = DatabaseConnector(root)
    _connectors["training"] = TrainingMonitor(root)
    _connectors["flywheel"] = FlywheelMonitor(root)


# ===================================================================
# HTML & ASSET ENDPOINTS
# ===================================================================


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard(request: Request) -> str:
    template_path = Path(__file__).resolve().parent / "templates" / "mission_control.html"
    if not template_path.exists():
        return "<h1>MoroAI Mission Control Dashboard Template Not Found</h1>"
    html = template_path.read_text(encoding="utf-8")
    nonce = csp_nonce(request)
    if nonce:
        html = re.sub(r"<script(?=[ >])", f'<script nonce="{nonce}"', html)
    return html


# ===================================================================
# REST API ENDPOINTS
# ===================================================================


@app.get("/api/health")
async def health_check() -> dict:
    # Liveness must not wait for external daemons or invent their readiness.
    return {
        "status": "healthy",
        "kind": "liveness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": {},
    }


@app.get("/api/system/overview")
async def system_overview() -> dict:
    docker: DockerConnector = _connectors.get("docker", DockerConnector())  # type: ignore
    ollama: OllamaConnector = _connectors.get("ollama", OllamaConnector())  # type: ignore
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    training: TrainingMonitor = _connectors.get("training", TrainingMonitor(get_project_root()))  # type: ignore
    flywheel: FlywheelMonitor = _connectors.get("flywheel", FlywheelMonitor(get_project_root()))  # type: ignore

    return {
        "docker": {
            "available": docker.available,
            "containers": docker.list_containers(),
        },
        "ollama": {
            "available": ollama.available,
            "models": ollama.list_models(),
        },
        "database": database.get_production_stats(),
        "training": training.get_active_training(),
        "flywheel": flywheel.get_status(),
        "runs": database.get_training_runs(),
        "registry": database.get_registered_models(),
        "lineage": database.get_state_lineage(),
    }


@app.get("/api/state/nodes")
async def state_nodes(node_type: str | None = None, limit: int = 50) -> dict:
    """Query state graph nodes."""
    from moro.state.manager import StateManager
    from moro.state.schema import NodeType

    project_root = get_project_root()
    state_manager = StateManager(project_root / ".moro" / "state.db")
    node_type_enum = NodeType(node_type) if node_type else None
    nodes = state_manager.query_nodes(node_type=node_type_enum, limit=limit)
    return {"nodes": nodes}


@app.get("/api/state/nodes/{node_id}/lineage")
async def state_lineage(node_id: str) -> dict:
    """Get the complete lineage of a node."""
    from moro.state.manager import StateManager

    project_root = get_project_root()
    state_manager = StateManager(project_root / ".moro" / "state.db")
    lineage = state_manager.trace_lineage(node_id)
    return lineage


@app.get("/api/registry/models")
async def registry_models_api() -> dict:
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    return {"models": database.get_registered_models()}


@app.post("/api/registry/models/{model_id}/promote")
async def registry_promote_model(model_id: str) -> dict:
    """Promote a model to production."""
    from moro.state.manager import StateManager

    project_root = get_project_root()
    state_manager = StateManager(project_root / ".moro" / "state.db")
    success = state_manager.promote_model_to_production(model_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to promote model")
    return {"status": "success", "model_id": model_id}


@app.get("/api/state/lineage")
async def state_lineage_api() -> dict:
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    return {"lineage": database.get_state_lineage()}


@app.get("/api/services/status")
async def services_status_api() -> dict:
    """Get status of all background services."""
    from moro.services.orchestrator import ServiceOrchestrator

    orchestrator = ServiceOrchestrator(get_project_root())
    return {"services": orchestrator.get_status()}


@app.post("/api/services/{service_name}/start")
async def services_start_api(service_name: str) -> dict:
    """Start a specific service."""
    from moro.services.orchestrator import ServiceOrchestrator

    orchestrator = ServiceOrchestrator(get_project_root())
    success = orchestrator.start_service(service_name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to start {service_name}")
    return {"status": "success", "service": service_name}


@app.post("/api/services/{service_name}/stop")
async def services_stop_api(service_name: str) -> dict:
    """Stop a specific service."""
    from moro.services.orchestrator import ServiceOrchestrator

    orchestrator = ServiceOrchestrator(get_project_root())
    success = orchestrator.stop_service(service_name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to stop {service_name}")
    return {"status": "success", "service": service_name}


@app.get("/api/docker/containers")
async def docker_containers() -> dict:
    docker: DockerConnector = _connectors.get("docker", DockerConnector())  # type: ignore
    if not docker.available:
        raise HTTPException(status_code=503, detail="Docker daemon is not available")
    return {"containers": docker.list_containers()}


@app.post("/api/docker/containers/{container_id}/start")
async def docker_start_container(container_id: str) -> dict:
    docker: DockerConnector = _connectors.get("docker", DockerConnector())  # type: ignore
    if not docker.available:
        raise HTTPException(status_code=503, detail="Docker is not available")
    success = docker.start_container(container_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start container")
    return {"status": "success", "container_id": container_id}


@app.post("/api/docker/containers/{container_id}/stop")
async def docker_stop_container(container_id: str) -> dict:
    docker: DockerConnector = _connectors.get("docker", DockerConnector())  # type: ignore
    if not docker.available:
        raise HTTPException(status_code=503, detail="Docker is not available")
    success = docker.stop_container(container_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to stop container")
    return {"status": "success", "container_id": container_id}


@app.get("/api/docker/containers/{container_id}/logs")
async def docker_container_logs(
    container_id: str,
    tail: int = Query(default=CONTAINER_LOGS_DEFAULT_TAIL, ge=1, le=CONTAINER_LOGS_MAX_TAIL),
) -> dict:
    docker: DockerConnector = _connectors.get("docker", DockerConnector())  # type: ignore
    if not docker.available:
        raise HTTPException(status_code=503, detail="Docker is not available")
    logs = docker.get_container_logs(container_id, tail)
    return {"container_id": container_id, "logs": logs}


@app.get("/api/ollama/models")
async def ollama_models() -> dict:
    ollama: OllamaConnector = _connectors.get("ollama", OllamaConnector())  # type: ignore
    return {"models": ollama.list_models()}


@app.get("/api/ollama/models/{model_name}")
async def ollama_model_info(model_name: str) -> dict:
    ollama: OllamaConnector = _connectors.get("ollama", OllamaConnector())  # type: ignore
    info = ollama.get_model_info(model_name)
    if not info:
        raise HTTPException(status_code=404, detail=f"Model not found: {model_name}")
    return info


class PromptPayload(BaseModel):
    model: str = "qwen2.5:1.5b"
    prompt: str


@app.post("/api/ollama/generate")
async def ollama_generate(payload: PromptPayload) -> dict:
    ollama: OllamaConnector = _connectors.get("ollama", OllamaConnector())  # type: ignore
    response = ollama.generate(payload.model, payload.prompt)
    return {"response": response}


@app.get("/api/database/production/stats")
async def database_production_stats() -> dict:
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    return database.get_production_stats()


@app.get("/api/database/production/logs")
async def database_production_logs(limit: int = 20) -> dict:
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    return {"logs": database.get_recent_logs(limit)}


@app.get("/api/training/runs")
async def training_runs() -> dict:
    database: DatabaseConnector = _connectors.get("database", DatabaseConnector(get_project_root()))  # type: ignore
    return {"runs": database.get_training_runs()}


@app.get("/api/training/active")
async def training_active() -> dict:
    training: TrainingMonitor = _connectors.get("training", TrainingMonitor(get_project_root()))  # type: ignore
    active = training.get_active_training()
    return {"active": active is not None, "details": active}


@app.get("/api/flywheel/status")
async def flywheel_status() -> dict:
    flywheel: FlywheelMonitor = _connectors.get("flywheel", FlywheelMonitor(get_project_root()))  # type: ignore
    return flywheel.get_status()


# ===================================================================
# EXPERIMENT TRACKING & ANALYTICS API ENDPOINTS
# ===================================================================


def _get_analytics_tracker() -> ExperimentTracker:
    root = get_project_root()
    return ExperimentTracker(root / ".moro" / "analytics.db")


def _get_analytics_viz_engine() -> VisualAnalyticsEngine:
    return VisualAnalyticsEngine(_get_analytics_tracker())


@app.get("/api/analytics/experiments")
async def analytics_experiments(status: str | None = None, limit: int = 50) -> dict:
    """List tracked experiments."""
    tracker = _get_analytics_tracker()
    experiments = tracker.list_experiments(status=status, limit=limit)
    return {"experiments": experiments}


@app.get("/api/analytics/experiments/{experiment_id}")
async def analytics_experiment_detail(experiment_id: str) -> dict:
    """Get detailed experiment information."""
    tracker = _get_analytics_tracker()
    experiment = tracker.get_experiment(experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    hyperparams = tracker.get_hyperparameters(experiment_id)
    metrics = tracker.get_metrics(experiment_id)

    return {
        "experiment": experiment,
        "hyperparameters": hyperparams,
        "metrics_count": len(metrics),
    }


@app.get("/api/analytics/experiments/{experiment_id}/metrics")
async def analytics_experiment_metrics(experiment_id: str) -> dict:
    """Get time-series metrics for an experiment."""
    tracker = _get_analytics_tracker()
    metrics = tracker.get_metrics(experiment_id)
    return {"metrics": metrics}


@app.get("/api/analytics/compare")
async def analytics_compare(experiment_ids: str) -> dict:
    """Compare multiple experiments side-by-side."""
    tracker = _get_analytics_tracker()
    ids = [i.strip() for i in experiment_ids.split(",") if i.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="No experiment IDs provided")
    return tracker.compare_experiments(ids)


@app.get("/api/analytics/viz/loss-curves")
async def analytics_loss_curves(experiment_ids: str, smoothing: int = 10) -> dict:
    """Generate loss curve visualization data."""
    viz_engine = _get_analytics_viz_engine()
    ids = [i.strip() for i in experiment_ids.split(",") if i.strip()]
    return viz_engine.generate_loss_curve_data(ids, smoothing_window=smoothing)


@app.get("/api/analytics/viz/quality-trend")
async def analytics_quality_trend(base_model: str | None = None, limit: int = 20) -> dict:
    """Generate quality trend visualization data."""
    viz_engine = _get_analytics_viz_engine()
    return viz_engine.generate_quality_trend_data(base_model, limit)


@app.get("/api/analytics/viz/hyperparameter-heatmap")
async def analytics_heatmap(
    x_param: str = "learning_rate",
    y_param: str = "lora_r",
    metric: str = "eval_delta",
) -> dict:
    """Generate hyperparameter heatmap data."""
    from moro.analytics.columns import AnalyticsColumnError, resolve_hyperparam, resolve_metric

    try:
        # Validate before initializing or querying the analytics database.
        resolve_hyperparam(x_param)
        resolve_hyperparam(y_param)
        resolve_metric(metric)
        viz_engine = _get_analytics_viz_engine()
        return viz_engine.generate_hyperparameter_heatmap(x_param, y_param, metric)
    except AnalyticsColumnError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/analytics/viz/resource-utilization/{experiment_id}")
async def analytics_resource_utilization(experiment_id: str) -> dict:
    """Generate resource utilization visualization data."""
    viz_engine = _get_analytics_viz_engine()
    return viz_engine.generate_resource_utilization_data(experiment_id)


@app.get("/api/analytics/viz/output-comparison")
async def analytics_output_comparison(
    experiment_ids: str,
    category: str | None = None,
    limit: int = 10,
) -> dict:
    """Generate model output comparison data."""
    viz_engine = _get_analytics_viz_engine()
    ids = [i.strip() for i in experiment_ids.split(",") if i.strip()]
    return viz_engine.generate_output_comparison(ids, prompt_category=category, limit=limit)


@app.get("/api/analytics/recommendations")
async def analytics_recommendations(recent: int = 10) -> dict:
    """Get recommendations for next experiment."""
    tracker = _get_analytics_tracker()
    recommendations = tracker.generate_recommendations(recent_experiments=recent)
    return {"recommendations": recommendations}


# ===================================================================
# WEBSOCKET ENDPOINTS (Real-time streaming)
# ===================================================================


@app.websocket("/ws/system/metrics")
async def ws_system_metrics(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time system metrics."""
    await websocket.accept()
    try:
        while True:
            overview = await system_overview()
            await websocket.send_json(
                {
                    "type": "metrics",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": overview,
                }
            )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/training/telemetry")
async def ws_training_telemetry(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time training telemetry."""
    await websocket.accept()
    try:
        while True:
            training: TrainingMonitor = _connectors.get(
                "training", TrainingMonitor(get_project_root())
            )  # type: ignore
            active = training.get_active_training()
            telemetry = (
                training.get_telemetry(active["run_id"]) if active and "run_id" in active else []
            )
            await websocket.send_json(
                {
                    "type": "telemetry",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": telemetry,
                }
            )
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/logs/stream")
async def ws_logs_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming logs."""
    await websocket.accept()
    try:
        while True:
            database: DatabaseConnector = _connectors.get(
                "database", DatabaseConnector(get_project_root())
            )  # type: ignore
            logs = database.get_recent_logs(5)
            await websocket.send_json(
                {
                    "type": "logs",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": logs,
                }
            )
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass


# Global alias for orchestrators and tests
mission_app = app
