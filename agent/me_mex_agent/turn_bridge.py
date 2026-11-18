"""Backend agent turn via REST or SSE."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

BACKEND_URL = os.getenv("ME_MEX_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


async def post_turn(
    *,
    text: str,
    thread_id: str,
    context_json: dict[str, Any],
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(
            f"{BACKEND_URL}/api/agent/turn",
            json={"text": text, "thread_id": thread_id, "context_json": context_json},
        )
        r.raise_for_status()
        return r.json()


async def post_resume(
    *,
    thread_id: str,
    approval_id: str,
    action: str,
    context_json: dict[str, Any],
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.post(
            f"{BACKEND_URL}/api/agent/resume",
            json={
                "thread_id": thread_id,
                "approval_id": approval_id,
                "action": action,
                "context_json": context_json,
            },
        )
        r.raise_for_status()
        return r.json()


async def stream_turn(
    *,
    text: str,
    thread_id: str,
    context_json: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    async with (
        httpx.AsyncClient(timeout=180.0) as client,
        client.stream(
            "POST",
            f"{BACKEND_URL}/api/agent/turn/stream",
            json={"text": text, "thread_id": thread_id, "context_json": context_json},
        ) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            yield json.loads(line[6:])


async def run_turn_with_reply(
    *,
    text: str,
    thread_id: str,
    context_json: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Consume SSE; return (reply_text, stream_events, turn_end)."""
    tokens: list[str] = []
    events: list[dict[str, Any]] = []
    turn_end: dict[str, Any] = {}
    async for chunk in stream_turn(text=text, thread_id=thread_id, context_json=context_json):
        events.append(chunk)
        if chunk.get("type") == "token":
            tokens.append(chunk.get("content") or "")
        if chunk.get("type") == "turn_end":
            turn_end = chunk
    reply = turn_end.get("reply") or "".join(tokens)
    if not reply:
        body = await post_turn(text=text, thread_id=thread_id, context_json=context_json)
        reply = body.get("reply") or ""
        turn_end = body
    return reply, events, turn_end
