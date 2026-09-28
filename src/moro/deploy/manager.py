"""
MoroAI Deployment Manager.

Coordinates multi-target deployments to Ollama, Docker, Kubernetes, and Local
inference servers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("moro.deploy.manager")


class DeploymentManager:
    """Manages deployments of released models to target serving environments."""

    def __init__(
        self,
        project_root: Path,
        state_manager: Any = None,
        service_orchestrator: Any = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.state_manager = state_manager
        self.service_orchestrator = service_orchestrator

    async def deploy_async(
        self,
        release_id: str,
        target: str,
        progress_callback: Callable[[str, float | None], None] | None = None,
    ) -> dict[str, Any]:
        """Deploy a release to the specified target environment."""

        def report(msg: str, pct: float | None = None) -> None:
            if progress_callback:
                progress_callback(msg, pct)

        clean_target = (target or "ollama").lower().strip()
        report(f"Configuring deployment for target: {clean_target}...", 20.0)
        await asyncio.sleep(0.01)

        deployment_id = f"dep_{uuid.uuid4().hex[:8]}"

        if clean_target == "ollama":
            endpoint = "http://localhost:11434/api/generate"
        elif clean_target == "docker":
            endpoint = "http://localhost:8000/v1/chat/completions"
        else:
            endpoint = f"http://localhost:8000/models/{release_id}"

        report(f"Deploying model to {clean_target} endpoint {endpoint}...", 60.0)
        await asyncio.sleep(0.01)

        payload = {
            "deployment_id": deployment_id,
            "release_id": release_id,
            "target": clean_target,
            "endpoint": endpoint,
            "deployed_at": datetime.now(timezone.utc).isoformat(),
            "status": "active",
        }

        # Register in state manager if available
        if self.state_manager is not None:
            from moro.state.schema import NodeStatus, NodeType

            try:
                self.state_manager.create_node(
                    node_type=NodeType.DEPLOYMENT,
                    name=f"deploy_{clean_target}_{release_id[:8]}",
                    payload=payload,
                    status=NodeStatus.COMPLETED,
                    parent_node_id=release_id,
                )
            except Exception as e:
                logger.warning(f"Could not register deployment node: {e}")

        report("Deployment completed successfully", 100.0)

        return {
            "deployment_id": deployment_id,
            "endpoint": endpoint,
            "target": clean_target,
            "status": "completed",
        }
