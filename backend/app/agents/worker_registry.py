"""Map worker kind → handler for background dispatch."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.db import ToolContext


def worker_handler(
    worker_kind: str,
) -> Callable[[ToolContext, str, dict[str, Any]], dict[str, Any]] | None:
    from app.agents import workers

    table: dict[str, Callable[..., dict[str, Any]]] = {
        "conversation": workers.conversation_worker,
        "gist": workers.gist_worker,
        "intradoc": workers.intradoc_worker,
        "link": workers.link_place_worker,
        "reorg": workers.reorg_recommend_worker,
        "retrieval": workers.retrieval_worker,
        "project_scope": workers.project_scope_worker,
        "scratch": workers.scratch_worker_with_context,
    }
    fn = table.get(worker_kind)
    if fn is None:
        return None

    def _wrapped(ctx: ToolContext, text: str, context: dict[str, Any]) -> dict[str, Any]:
        if worker_kind in ("link", "reorg"):
            if worker_kind == "link":
                return workers.link_place_worker(ctx, context)
            return workers.reorg_recommend_worker(ctx)
        if worker_kind == "conversation":
            return workers.conversation_worker(ctx, text)
        return fn(ctx, text, context)

    return _wrapped
