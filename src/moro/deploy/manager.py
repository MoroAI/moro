"""Deployment integration boundary. Serving requires an implemented target adapter."""

from pathlib import Path

from moro.core.errors import ExportError


class DeploymentManager:
    def __init__(self, project_root: Path, state_manager=None, service_orchestrator=None):
        self.project_root = Path(project_root)
        self.state_manager = state_manager
        self.service_orchestrator = service_orchestrator

    async def deploy_async(self, release_id, target, progress_callback=None):
        raise ExportError(
            "Automatic serving deployment is not implemented. Use `moro deploy ollama` "
            "to prepare a verified package, then import it into Ollama and verify inference. "
            "No endpoint has been created."
        )
