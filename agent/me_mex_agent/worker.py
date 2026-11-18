"""Long-lived LiveKit worker — bridges room audio/data to Colab STT/TTS and backend graph."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

try:
    from livekit import rtc
    from livekit.agents import JobContext, WorkerOptions, cli
except ImportError:  # pragma: no cover
    rtc = None
    JobContext = Any  # type: ignore[misc,assignment]
    WorkerOptions = Any
    cli = None


BACKEND_URL = os.getenv("ME_MEX_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def _colab_speech_base() -> str:
    raw = os.getenv("COLAB_INFERENCE_BASE_URL", "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/v1"):
        return raw[:-3].rstrip("/")
    return raw


SPEECH_BASE = _colab_speech_base()


async def handle_data_message(payload: bytes, ctx: JobContext) -> None:
    """Handle approve/cancel + context_json from frontend data channel."""
    try:
        msg = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        return
    if msg.get("type") == "agent_turn":
        async with httpx.AsyncClient(timeout=180.0) as client:
            await client.post(
                f"{BACKEND_URL}/api/agent/turn",
                json={
                    "text": msg.get("text", ""),
                    "thread_id": msg.get("thread_id", "livekit"),
                    "context_json": msg.get("context_json") or {},
                },
            )


async def entrypoint(ctx: JobContext) -> None:
    if rtc is None:
        raise RuntimeError("livekit-agents not installed")
    room = ctx.room
    await room.connect()

    @room.on("data_received")
    def _on_data(data: rtc.DataPacket) -> None:
        asyncio.create_task(handle_data_message(data.data, ctx))


def main() -> None:
    if cli is None:
        raise RuntimeError("Install livekit-agents to run the worker")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
