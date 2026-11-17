from __future__ import annotations

from typing import Any

from app.config import settings
from app.db import ToolContext
from app.models import PendingApproval, new_id
from app.services.timing import timed_tool


@timed_tool
def enqueue_pending_approval(
    ctx: ToolContext,
    *,
    approval_type: str,
    title: str,
    payload: dict[str, Any],
) -> str:
    item = PendingApproval(
        _id=new_id("appr"),
        project_id=ctx.project_id,
        thread_id=ctx.thread_id,
        approval_type=approval_type,
        title=title,
        payload=payload,
    )
    return ctx.store.enqueue_approval(item)


def list_pending_approvals(ctx: ToolContext) -> dict:
    items = ctx.store.list_pending(ctx.project_id, ctx.thread_id)
    return {
        "items": [
            {
                "id": i.id,
                "approval_type": i.approval_type,
                "title": i.title,
                "payload": i.payload,
            }
            for i in items
        ]
    }


def get_suggested_next_actions(ctx: ToolContext) -> dict:
    """Deterministic nudges from graph state (degree, orphans)."""
    nodes = ctx.store.list_nodes(ctx.project_id)
    suggestions: list[dict] = []
    for n in nodes:
        if (
            n.node_kind.value == "CONCEPT_M"
            and ctx.store.degree(n.id) > settings.DEGREE_THRESHOLD
        ):
            suggestions.append(
                {"type": "reorg", "title": f"Hub crowded: {n.title}", "node_id": n.id}
            )
    return {"suggestions": suggestions[:5]}


def open_passages(
    ctx: ToolContext, *, passage_ids: list[str], max_chars: int = 8000
) -> dict:
    passages = ctx.store.get_passages(passage_ids)
    text = "\n\n".join(p["text_content"] for p in passages)
    return {"text": text[:max_chars], "passage_ids": passage_ids}
