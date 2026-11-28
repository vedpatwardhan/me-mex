"""Slim Supervisor routing payload (dock turn path)."""

from __future__ import annotations

from typing import Any


def needs_full_graph_candidates(context: dict[str, Any] | None) -> bool:
    ctx = context or {}
    fields = ctx.get("custom_fields") or {}
    if fields.get("root_id") or ctx.get("pinned_root_id"):
        return True
    return bool(ctx.get("selected_node_ids"))


def slim_routing_context(context: dict[str, Any]) -> dict[str, Any]:
    """Drop bulky copies from Supervisor human message while keeping routing essentials."""
    session = context.get("session_state") or {}
    slim_session = {
        "active_jobs": session.get("active_jobs") or [],
        "recent_jobs": session.get("recent_jobs") or [],
        "pending_approval_count": session.get("pending_approval_count") or 0,
        "completed_worker_results": session.get("completed_worker_results") or [],
    }
    memory = context.get("routing_memory") or {}
    slim_memory = {
        "summary": (memory.get("summary") or "")[:800],
        "recent_turns": (memory.get("recent_turns") or [])[-6:],
        "focus_root": memory.get("focus_root"),
        "current_source": memory.get("current_source"),
    }
    return {
        "custom_fields": context.get("custom_fields") or {},
        "selected_node_ids": context.get("selected_node_ids") or [],
        "graph_candidates": context.get("graph_candidates") or [],
        "routing_memory": slim_memory,
        "session_state": slim_session,
        "project_scope_status": context.get("project_scope_status"),
        "scope_approval_pending": context.get("scope_approval_pending"),
        "pinned_root_id": context.get("pinned_root_id"),
        "planning_contract": context.get("planning_contract"),
    }
