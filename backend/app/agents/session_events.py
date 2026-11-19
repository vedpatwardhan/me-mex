"""In-memory session event bus for SSE (voice proactive / job updates)."""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from queue import Queue
from typing import Any

_lock = threading.Lock()
_subscribers: dict[str, list[tuple[asyncio.AbstractEventLoop, Queue]]] = {}


def publish_session_event(thread_id: str, event: dict[str, Any]) -> None:
    with _lock:
        subs = list(_subscribers.get(thread_id, []))
    for loop, q in subs:
        try:
            loop.call_soon_threadsafe(q.put_nowait, event)
        except RuntimeError:
            pass


async def subscribe_session_events(thread_id: str) -> AsyncIterator[dict[str, Any]]:
    loop = asyncio.get_running_loop()
    q: Queue = Queue(maxsize=64)
    with _lock:
        _subscribers.setdefault(thread_id, []).append((loop, q))
    try:
        yield {"type": "connected", "thread_id": thread_id}
        while True:
            event = await loop.run_in_executor(None, q.get)
            yield event
    finally:
        with _lock:
            lst = _subscribers.get(thread_id, [])
            _subscribers[thread_id] = [pair for pair in lst if pair[1] is not q]


def format_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"
