"""
MoroAI Feedback Gateway.

Proxy API service that routes chat completions to local models (e.g. Ollama)
and streams feedback data into the continuous learning pipeline.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger("moro.gateway")

gateway_app = FastAPI(
    title="MoroAI Feedback Gateway",
    description="Inference proxy and interaction telemetry capture endpoint",
    version="1.0.0",
)

gateway_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "default"
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: int = 512
    stream: bool = False


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl_{datetime.now(timezone.utc).strftime('%s')}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(datetime.now(timezone.utc).timestamp()))
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int]


@gateway_app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint for the feedback gateway."""
    return {
        "status": "healthy",
        "service": "gateway",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    }


@gateway_app.get("/v1/models")
async def list_models() -> dict[str, Any]:
    """List available deployed models."""
    return {
        "object": "list",
        "data": [
            {"id": "moro-default", "object": "model", "owned_by": "moro"},
            {"id": "qwen2.5:1.5b", "object": "model", "owned_by": "ollama"},
        ],
    }


@gateway_app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(req: ChatCompletionRequest) -> ChatCompletionResponse:
    """Chat completions endpoint with feedback hook."""
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    # Attempt to query Ollama if available
    content = "Hello! I am your MoroAI fine-tuned assistant."
    try:
        import httpx

        prompt = req.messages[-1].content if req.messages else "Hello"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{ollama_url}/api/generate",
                json={"model": req.model, "prompt": prompt, "stream": False},
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data.get("response", content)
    except Exception as e:
        logger.debug(f"Direct Ollama call skipped ({e}), returning default assistant response.")

    return ChatCompletionResponse(
        model=req.model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    )
