"""Map LangGraph astream_events v3 to dock-facing DTOs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


def event_to_dock_payload(ev: dict[str, Any]) -> dict[str, Any] | None:
    kind = ev.get("event")
    data = ev.get("data") or {}
    if kind == "on_chat_model_stream":
        chunk = data.get("chunk")
        if chunk and hasattr(chunk, "content") and chunk.content:
            return {"type": "token", "content": chunk.content}
    if kind == "on_custom_event":
        return {"type": "custom", **(data if isinstance(data, dict) else {"data": data})}
    if kind in ("on_chain_end", "on_chain_start"):
        name = ev.get("name") or data.get("name")
        if name:
            return {"type": "task", "name": name, "phase": kind}
    return None


async def iter_dock_events(
    astream_events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    async for ev in astream_events:
        payload = event_to_dock_payload(ev)
        if payload:
            yield payload
