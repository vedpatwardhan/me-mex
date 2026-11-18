"""Map LangGraph astream_events v3 to dock-facing DTOs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


def event_to_dock_payload(ev: dict[str, Any]) -> dict[str, Any] | None:
    kind = ev.get("event") or ""
    data = ev.get("data") or {}
    if kind == "on_chat_model_stream":
        chunk = data.get("chunk")
        if chunk and hasattr(chunk, "content") and chunk.content:
            return {"type": "token", "content": chunk.content}
    if kind == "on_custom_event":
        return {"type": "custom", **(data if isinstance(data, dict) else {"data": data})}
    if kind == "on_chain_stream" and ev.get("name") == "hitl_gate":
        return None
    if "interrupt" in kind.lower():
        interrupt_data = data if isinstance(data, dict) else {"data": data}
        return {"type": "approval", **interrupt_data}
    if kind in ("on_chain_end", "on_chain_start"):
        name = ev.get("name") or data.get("name")
        if name:
            payload: dict[str, Any] = {"type": "task", "name": name, "phase": kind}
            if kind == "on_chain_end" and name == "worker":
                out = {}
                if isinstance(data, dict):
                    out = data.get("output") or data.get("chunk", {}).get("output") or {}
                if isinstance(out, dict):
                    if out.get("approval_id"):
                        payload = {
                            "type": "approval",
                            "approval_id": out["approval_id"],
                            "title": out.get("title", "Pending approval"),
                            "detail": out.get("reply"),
                        }
                    elif out.get("reply"):
                        payload["type"] = "reply"
                        payload["content"] = out.get("reply")
            return payload
    return None


async def iter_dock_events(
    astream_events: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    async for ev in astream_events:
        payload = event_to_dock_payload(ev)
        if payload:
            yield payload
