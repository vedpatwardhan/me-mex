"""Structural Supervisor shortcuts from authoritative custom_fields (no utterance regex)."""

from __future__ import annotations

from typing import Any

from app.agents.source_reference import resolve_source_reference
from app.llm.schemas import WorkerRoute
from app.models import Project


def _empty_project_scope_route(text: str, project: Project) -> WorkerRoute | None:
    """P1 scope onboarding when introduction is empty (no Supervisor JSON required)."""
    if (project.introduction or "").strip():
        return None
    normalized = " ".join(text.lower().split())
    if not normalized:
        return None
    triggers = (
        "my project scope",
        "project scope is",
        "save scope",
        "define my scope",
        "define the project scope",
    )
    if not any(phrase in normalized for phrase in triggers):
        return None
    return WorkerRoute(
        worker="project_scope",
        intent="scope_conversation",
        dispatch=True,
    )


def _retrieval_route(text: str, fields: dict[str, Any]) -> WorkerRoute | None:
    """W11: explicit graph seed in custom fields + relation question → RetrievalWorker."""
    if not str(fields.get("query_node_id") or "").strip():
        return None
    normalized = " ".join(text.lower().split())
    if not normalized:
        return None
    triggers = (
        "what relates",
        "relates to",
        "related to",
        "related nodes",
        "highlight",
        "subgraph",
        "connections in",
        "what connects",
        "explore the graph",
    )
    if any(phrase in normalized for phrase in triggers):
        return WorkerRoute(worker="retrieval", intent="retrieval", dispatch=True)
    return None


def _link_route_from_graph_context(text: str, context: dict[str, Any]) -> WorkerRoute | None:
    memory = context.get("routing_memory") or {}
    focus = (memory.get("focus_root") or {}).get("id") or context.get("pinned_root_id")
    if not focus:
        return None
    lowered = text.lower()
    if not any(word in lowered for word in ("connect", "link", "place", "fit")):
        return None
    candidates = context.get("graph_candidates") or []
    target_ids: list[str] = []
    for row in candidates:
        cid = str(row.get("id") or "")
        title = str(row.get("title") or "").lower()
        if not cid or cid == focus:
            continue
        title_tokens = [token for token in title.replace("-", " ").split() if len(token) > 2]
        if title and title in lowered:
            target_ids.append(cid)
            continue
        if any(token in lowered for token in title_tokens):
            target_ids.append(cid)
    if len(target_ids) != 1:
        return None
    return WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        root_id=str(focus),
        target_ids=target_ids,
    )


def authoritative_worker_route(
    text: str,
    fields: dict[str, Any],
    project: Project,
    *,
    context: dict[str, Any] | None = None,
) -> WorkerRoute | None:
    """Return a route when custom_fields or project state make the worker unambiguous."""
    if fields.get("force_gist_commit"):
        source = resolve_source_reference(text, fields)
        return WorkerRoute(
            worker="gist",
            intent="commit_gist",
            dispatch=True,
            title=fields.get("title"),
            content=fields.get("gist"),
            source_field=source.field_name,
            source_reference=source.url,
        )
    if fields.get("force_project_scope") and not (project.introduction or "").strip():
        return WorkerRoute(
            worker="project_scope",
            intent="scope_conversation",
            dispatch=True,
        )
    if scope := _empty_project_scope_route(text, project):
        return scope
    if fields.get("resume_job_id"):
        return WorkerRoute(worker="conversation", intent="status", dispatch=False)
    if retrieval := _retrieval_route(text, fields):
        return retrieval
    if fields.get("promote_todo_id"):
        return WorkerRoute(
            worker="scratch",
            intent="promote_todo",
            dispatch=True,
            target_id=str(fields["promote_todo_id"]),
        )
    if fields.get("root_id") and fields.get("raw_text"):
        return WorkerRoute(
            worker="intradoc",
            intent="source_analysis",
            dispatch=True,
            source_field="raw_text",
        )
    if context and (
        link := _link_route_from_graph_context(
            text, {**context, "pinned_root_id": fields.get("root_id")}
        )
    ):
        return link
    return None
