"""Authenticated proxy to Ollama with truthful failures and measured usage."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from moro.dashboard.security import install_security

gateway_app = FastAPI(title="MoroAI Gateway", version="1.0.0")
install_security(gateway_app)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=100_000)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    model: str = Field(min_length=1, max_length=256)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(512, ge=1, le=32768)
    stream: bool = False


async def ollama_request(method, path, payload=None):
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.request(method, base + path, json=payload)
        if response.status_code >= 400:
            raise HTTPException(502, f"Ollama returned HTTP {response.status_code}")
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Ollama is unavailable or returned an invalid response") from exc


@gateway_app.get("/health")
async def health_check() -> dict[str, Any]:
    return {"status": "healthy", "service": "gateway", "kind": "liveness"}


@gateway_app.get("/v1/models")
async def list_models():
    data = await ollama_request("GET", "/api/tags")
    if not isinstance(data, dict) or not isinstance(data.get("models"), list):
        raise HTTPException(502, "Invalid Ollama model inventory")
    return {
        "object": "list",
        "data": [
            {"id": model["name"], "object": "model", "owned_by": "ollama"}
            for model in data["models"]
            if isinstance(model, dict) and isinstance(model.get("name"), str)
        ],
    }


@gateway_app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if req.stream:
        raise HTTPException(422, "Streaming is not implemented")
    data = await ollama_request(
        "POST",
        "/api/chat",
        {
            "model": req.model,
            "messages": [message.model_dump() for message in req.messages],
            "stream": False,
            "options": {"temperature": req.temperature, "num_predict": req.max_tokens},
        },
    )
    message = data.get("message") if isinstance(data, dict) else None
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise HTTPException(502, "Ollama did not return an assistant message")
    prompt_tokens, completion_tokens = data.get("prompt_eval_count"), data.get("eval_count")
    usage = None
    if all(isinstance(value, int) and value >= 0 for value in (prompt_tokens, completion_tokens)):
        usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    return {
        "id": "chatcmpl_" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": message["content"]},
                "finish_reason": "length" if data.get("done_reason") == "length" else "stop",
            }
        ],
        "usage": usage,
    }
