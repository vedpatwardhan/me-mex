"""HITL audit logs and label completion for decision traces."""

from __future__ import annotations

import logging

from app.db import ToolContext
from app.models import PendingApproval
from app.services.decision_trace_writer import append_decision_trace_row, query_node_dict

logger = logging.getLogger("memex.v2.hitl")


def log_hitl_action(
    *,
    action: str,
    approval_id: str,
    thread_id: str,
    project_id: str,
    approval_type: str | None = None,
) -> None:
    logger.info(
        "hitl action=%s approval_id=%s thread_id=%s project_id=%s approval_type=%s",
        action,
        approval_id,
        thread_id,
        project_id,
        approval_type or "",
    )


def _normalize_labels(frontier_ids: list[str], positive: set[str]) -> dict[str, float]:
    if not frontier_ids:
        return {}
    if not positive:
        u = 1.0 / len(frontier_ids)
        return {fid: u for fid in frontier_ids}
    labels = {fid: (1.0 if fid in positive else 0.0) for fid in frontier_ids}
    total = sum(labels.values())
    if total <= 0:
        u = 1.0 / len(frontier_ids)
        return {fid: u for fid in frontier_ids}
    return {k: v / total for k, v in labels.items()}


def append_hitl_label_trace(
    ctx: ToolContext,
    item: PendingApproval,
    *,
    chosen_ids: list[str] | None = None,
) -> None:
    """Append label_relevance after user approves a scored decision."""
    payload = item.payload or {}
    approval_type = item.approval_type

    if approval_type == "placement":
        candidates = payload.get("candidates") or []
        frontier_ids = [c[0] if isinstance(c, (list, tuple)) else str(c) for c in candidates]
        if not frontier_ids:
            return
        root_id = payload.get("root_id", "")
        positive = set(chosen_ids or [])
        row = {
            "scenario": "placement_hitl",
            "thread_id": ctx.thread_id,
            "approval_id": item.id,
            "query_node": {"id": root_id, "title": "", "node_kind": "ROOT"},
            "frontier": [{"id": fid, "title": "", "node_kind": ""} for fid in frontier_ids],
            "label_relevance": _normalize_labels(frontier_ids, positive),
            "user_chosen_ids": list(positive),
        }
        append_decision_trace_row(ctx.project_id, row)
        return

    if approval_type == "reorg":
        proposal_id = payload.get("proposal_id")
        if proposal_id:
            doc = ctx.store._db.reorg_proposals.find_one({"_id": proposal_id})
            if doc:
                payload = {**payload, **{k: v for k, v in doc.items() if k != "_id"}}
        moves = payload.get("moves") or []
        if isinstance(moves, list) and moves:
            frontier_ids = [m.get("node_id") for m in moves if m.get("node_id")]
        else:
            scores = payload.get("scores") or []
            frontier_ids = [s[0] if isinstance(s, (list, tuple)) else str(s) for s in scores]
        if not frontier_ids:
            return
        hub_id = (payload.get("before") or {}).get("hub_id", "")
        row = {
            "scenario": "reorg_hitl",
            "thread_id": ctx.thread_id,
            "approval_id": item.id,
            "query_node": query_node_dict({"id": hub_id, "title": "", "node_kind": "CONCEPT_M"}),
            "frontier": [{"id": fid, "title": "", "node_kind": ""} for fid in frontier_ids],
            "label_relevance": _normalize_labels(frontier_ids, set(frontier_ids)),
            "user_chosen_ids": frontier_ids,
        }
        append_decision_trace_row(ctx.project_id, row)
