"""Ollama runtime inspection and truthful serving operations."""

from __future__ import annotations

import os
import time

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from moro.dashboard.utils import get_project_root

router = APIRouter(prefix="/api/deployment", tags=["deployment"])


class DeploymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str = Field(min_length=1, max_length=256)
    target: str = "ollama"
    version: str = "latest"


async def _request(method, path, payload=None):
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, base + path, json=payload)
        if response.status_code >= 400:
            raise HTTPException(502, f"Ollama returned HTTP {response.status_code}")
        return response.json() if response.content else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Ollama is unavailable or returned an invalid response") from exc


async def _check_ollama():
    try:
        data = await _request("GET", "/api/tags")
        if not isinstance(data, dict) or not isinstance(data.get("models"), list):
            raise HTTPException(502, "Invalid Ollama inventory")
        return {"available": True, "models": data["models"]}
    except HTTPException:
        return {"available": False, "models": []}


@router.get("/status")
async def get_deployment_status():
    info = await _check_ollama()
    return {"ollama": {**info, "model_count": len(info["models"])}, "deployments": []}


@router.post("/deploy")
async def deploy_model(request: DeploymentRequest):
    raise HTTPException(
        501,
        "Automatic serving deployment is not implemented. Prepare and import a verified release using the CLI.",
    )


@router.post("/undeploy/{deployment_id}")
async def undeploy_model(deployment_id: str):
    raise HTTPException(404, "No managed deployment exists for this ID")


@router.get("/ollama/models")
async def list_ollama_models():
    return await _check_ollama()


@router.post("/ollama/pull")
async def pull_ollama_model(model_name: str):
    from moro.config.loader import load_config

    if load_config(get_project_root() / "moro.yaml").project.privacy_mode == "local_only":
        raise HTTPException(409, "Model downloads are disabled in local_only mode")
    data = await _request("POST", "/api/pull", {"name": model_name, "stream": False})
    if data.get("status") != "success":
        raise HTTPException(502, "Ollama did not confirm download completion")
    return {"status": "success", "model": model_name}


@router.delete("/ollama/models/{model_name}")
async def delete_ollama_model(model_name: str):
    await _request("DELETE", "/api/delete", {"name": model_name})
    return {"status": "deleted", "model": model_name}


@router.post("/ollama/test")
async def test_ollama_model(model_name: str, prompt: str = "Hello! Tell me about local AI."):
    started = time.monotonic()
    data = await _request(
        "POST", "/api/generate", {"model": model_name, "prompt": prompt, "stream": False}
    )
    if not isinstance(data.get("response"), str):
        raise HTTPException(502, "Ollama did not return generated text")
    return {
        "status": "success",
        "response": data["response"],
        "latency_ms": round((time.monotonic() - started) * 1000, 2),
        "model": model_name,
    }
