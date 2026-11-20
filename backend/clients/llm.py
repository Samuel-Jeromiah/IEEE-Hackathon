"""OpenAI-compatible client for llama-server (VLM and coder).

Thinking is always off. Structured calls use json_schema. Images are data URLs.
"""
from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from backend.config import load_models_config

# Default caps; workers may pass a smaller max_tokens.
DEFAULT_MAX_TOKENS = 1024


def _server_base(role: str) -> str:
    srv = load_models_config()["servers"][role]
    return f"http://{srv['host']}:{srv['port']}/v1"


def image_data_url(path: Path, mime: str = "image/jpeg") -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _chat_body(
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    max_tokens: int,
    json_schema: dict[str, Any] | None,
    stream: bool,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if json_schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": json_schema, "strict": False},
        }
    return body


async def chat(
    role: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    json_schema: dict[str, Any] | None = None,
    timeout_s: float = 60.0,
) -> str:
    """Non-streaming chat completion; returns the assistant message content."""
    url = f"{_server_base(role)}/chat/completions"
    body = _chat_body(messages, temperature=temperature, max_tokens=max_tokens,
                      json_schema=json_schema, stream=False)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"] or ""


async def chat_json(
    role: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    *,
    temperature: float = 0.0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    raw = await chat(role, messages, temperature=temperature, max_tokens=max_tokens,
                     json_schema=schema, timeout_s=timeout_s)
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].lstrip()
    return json.loads(text)


async def chat_stream(
    role: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = 60.0,
    on_delta: Callable[[str], None] | None = None,
) -> str:
    """Stream tokens; optionally notify on each delta. Returns the full text."""
    url = f"{_server_base(role)}/chat/completions"
    body = _chat_body(messages, temperature=temperature, max_tokens=max_tokens,
                      json_schema=None, stream=True)
    parts: list[str] = []
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        async with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                chunk = json.loads(payload)
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    parts.append(piece)
                    if on_delta:
                        on_delta(piece)
    return "".join(parts)


async def aiter_chat_stream(
    role: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout_s: float = 60.0,
) -> AsyncIterator[str]:
    url = f"{_server_base(role)}/chat/completions"
    body = _chat_body(messages, temperature=temperature, max_tokens=max_tokens,
                      json_schema=None, stream=True)
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        async with client.stream("POST", url, json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                chunk = json.loads(payload)
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    yield piece
