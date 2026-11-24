"""Backend agent turn via REST or SSE."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Awaitable, Callable
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


def _use_voice_conversation_stream(context_json: dict[str, Any]) -> bool:
    if context_json.get("voice_turn") is True:
        return True
    return str(context_json.get("voice_turn", "")).lower() in ("1", "true", "yes")


async def post_abort_turn(*, turn_id: str, thread_id: str) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{BACKEND_URL}/api/voice/conversation/abort",
            json={"turn_id": turn_id, "thread_id": thread_id},
        )


async def stream_turn(
    *,
    text: str,
    thread_id: str,
    context_json: dict[str, Any],
    cancel_check: Callable[[], bool] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    path = (
        "/api/voice/conversation/stream"
        if _use_voice_conversation_stream(context_json)
        else "/api/agent/turn/stream"
    )
    payload = context_json
    if path.endswith("conversation/stream"):
        payload = {**context_json, "voice_turn": True}
    async with (
        httpx.AsyncClient(timeout=180.0) as client,
        client.stream(
            "POST",
            f"{BACKEND_URL}{path}",
            json={"text": text, "thread_id": thread_id, "context_json": payload},
        ) as response,
    ):
        response.raise_for_status()
        async for line in response.aiter_lines():
            if cancel_check and cancel_check():
                await response.aclose()
                break
            if not line.startswith("data: "):
                continue
            yield json.loads(line[6:])


async def stream_session_events(
    *,
    project_id: str,
    thread_id: str,
) -> AsyncIterator[dict[str, Any]]:
    url = (
        f"{BACKEND_URL}/api/agent/session/events"
        f"?project_id={httpx.QueryParams({'project_id': project_id})['project_id']}"
        f"&thread_id={httpx.QueryParams({'thread_id': thread_id})['thread_id']}"
    )
    async with (
        httpx.AsyncClient(timeout=None) as client,
        client.stream("GET", url) as response,
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
    on_chunk: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """Consume SSE; return (reply_text, stream_events, turn_end)."""
    tokens: list[str] = []
    events: list[dict[str, Any]] = []
    turn_end: dict[str, Any] = {}
    async for chunk in stream_turn(
        text=text,
        thread_id=thread_id,
        context_json=context_json,
        cancel_check=cancel_check,
    ):
        if cancel_check and cancel_check():
            break
        events.append(chunk)
        if on_chunk is not None:
            await on_chunk(chunk)
        if chunk.get("type") == "token":
            if chunk.get("source") not in (None, "conversation"):
                continue
            tokens.append(chunk.get("content") or "")
        if chunk.get("type") == "turn_end":
            turn_end = chunk
    reply = turn_end.get("reply") or "".join(tokens)
    if not reply:
        body = await post_turn(text=text, thread_id=thread_id, context_json=context_json)
        reply = body.get("reply") or ""
        turn_end = body
    return reply, events, turn_end
