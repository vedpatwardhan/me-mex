"""Voice dispatch policy (04 §12.11, plan phase 0)."""

from __future__ import annotations

import asyncio
from typing import Any

from app.errors import NotFoundError
from app.llm.schemas import WorkerRoute


def is_voice_turn(context_json: dict[str, Any] | None) -> bool:
    if not context_json:
        return False
    if context_json.get("voice_turn") is True:
        return True
    return str(context_json.get("voice_turn", "")).lower() in ("1", "true", "yes")


def needs_voice_dispatch(
    decision: WorkerRoute,
    *,
    voice_turn: bool,
    scope_blocked: bool = False,
) -> bool:
    return bool(
        voice_turn and not scope_blocked and decision.dispatch and decision.worker != "conversation"
    )


def normalize_link_decision(decision: WorkerRoute, context: dict[str, Any]) -> WorkerRoute:
    """Validate Supervisor-selected link IDs and fill a missing source from structured focus."""
    if decision.worker != "link" or decision.intent != "link":
        return decision

    candidates = {
        str(node.get("id")): node
        for node in (context.get("graph_candidates") or [])
        if node.get("id")
    }
    fields = context.get("custom_fields") or {}
    memory = context.get("routing_memory") or {}
    current_source = memory.get("current_source") or {}
    focus_root = memory.get("focus_root") or {}
    selected_ids = [str(node_id) for node_id in (context.get("selected_node_ids") or [])]

    explicit_root = fields.get("root_id") or decision.root_id
    root_id = str(explicit_root) if explicit_root else None
    if not root_id or candidates.get(root_id, {}).get("node_kind") != "ROOT":
        selected_roots = [
            node_id
            for node_id in selected_ids
            if candidates.get(node_id, {}).get("node_kind") == "ROOT"
        ]
        if len(selected_roots) == 1:
            root_id = selected_roots[0]
        else:
            current_root_id = str(current_source.get("root_id") or "")
            if current_root_id and candidates.get(current_root_id, {}).get("node_kind") == "ROOT":
                root_id = current_root_id
            elif current_source and not current_root_id:
                root_id = None
            else:
                focus_root_id = str(focus_root.get("id") or "")
                if focus_root_id and candidates.get(focus_root_id, {}).get("node_kind") == "ROOT":
                    root_id = focus_root_id
                else:
                    roots = [
                        node_id
                        for node_id, node in candidates.items()
                        if node.get("node_kind") == "ROOT"
                    ]
                    root_id = roots[0] if len(roots) == 1 else None

    target_ids: list[str] = []
    if decision.root_id:
        misplaced_root = candidates.get(str(decision.root_id))
        if (
            misplaced_root
            and misplaced_root.get("node_kind") not in {"ROOT", "CONCEPT_I"}
            and str(decision.root_id) != root_id
        ):
            target_ids.append(str(decision.root_id))
    for target_id in decision.target_ids or []:
        node_id = str(target_id)
        node = candidates.get(node_id)
        # A ROOT in this list is commonly the model's reversed source field.
        # A user-selected ROOT target is represented by the singular target_id.
        if node and node_id != root_id and node.get("node_kind") not in {"CONCEPT_I", "ROOT"}:
            target_ids.append(node_id)

    if decision.target_id:
        target_id = str(decision.target_id)
        node = candidates.get(target_id)
        if node and target_id != root_id and node.get("node_kind") != "CONCEPT_I":
            target_ids.append(target_id)
    for node_id in selected_ids:
        node = candidates.get(node_id)
        if node and node_id != root_id and node.get("node_kind") != "CONCEPT_I":
            target_ids.append(node_id)
    target_ids = list(dict.fromkeys(target_ids))

    if root_id:
        return decision.model_copy(update={"root_id": root_id, "target_ids": target_ids})

    if current_source and not current_source.get("root_id"):
        clarification = (
            "The paper currently being processed does not have a ROOT in the graph yet. "
            "Approve its gist or deep-read first, or select an existing ROOT to connect."
        )
    else:
        roots = [
            str(node.get("title") or node_id)
            for node_id, node in candidates.items()
            if node.get("node_kind") == "ROOT"
        ]
        available = ", ".join(roots[:5])
        clarification = "Which paper ROOT should I connect, and which graph node should it link to?"
        if available:
            clarification = f"Which paper ROOT should I connect? Available ROOTs: {available}."
    return decision.model_copy(
        update={
            "worker": "conversation",
            "intent": "conversation",
            "dispatch": False,
            "root_id": None,
            "target_ids": None,
            "source_error": "link_resolution",
            "content": clarification,
        }
    )


def resolve_voice_route(
    *,
    store,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict[str, Any],
) -> tuple[WorkerRoute, str, bool]:
    from app.agents.context_preprocessor import (
        apply_custom_fields_to_text,
        block_graph_writes_without_scope,
        graph_candidates_for_supervisor,
        prioritize_project_scope_until_complete,
    )
    from app.agents.workers import route_intent

    project = store.get_project(project_id)
    effective = apply_custom_fields_to_text(text, context_json or {})
    routing_context = dict(context_json or {})
    candidates = routing_context.get("graph_candidates") or graph_candidates_for_supervisor(
        store, project_id
    )
    memory = routing_context.get("routing_memory") or {}
    current_source = memory.get("current_source") or {}
    focus_root = memory.get("focus_root") or {}
    focused_id = str(current_source.get("root_id") or focus_root.get("id") or "")
    if focused_id and not any(node.get("id") == focused_id for node in candidates):
        try:
            focused_node = store.get_node(focused_id)
        except (
            NotFoundError
        ):  # Stale focus references are ignored; validation will request clarification.
            focused_node = None
        if focused_node and focused_node.project_id == project_id:
            candidates.append(
                {
                    "id": focused_node.id,
                    "title": focused_node.title[:180],
                    "node_kind": focused_node.node_kind.value,
                }
            )
    routing_context["graph_candidates"] = candidates
    routing_context["scope_approval_pending"] = any(
        item.approval_type == "project_scope" for item in store.list_pending(project_id, thread_id)
    )
    decision = route_intent(effective, routing_context, project)
    decision = normalize_link_decision(decision, routing_context)
    worker = prioritize_project_scope_until_complete(
        project.introduction,
        decision.worker,
        context_json,
    )
    if worker != decision.worker:
        decision = decision.model_copy(
            update={
                "worker": worker,
                "intent": "scope_conversation",
                "dispatch": True,
            }
        )
    scope_blocked = block_graph_writes_without_scope(project.introduction, worker)
    if scope_blocked:
        worker = "project_scope"
        decision = decision.model_copy(
            update={
                "worker": worker,
                "intent": "scope_conversation",
                "dispatch": True,
            }
        )
    return decision, effective, scope_blocked


async def resolve_voice_route_async(**kwargs):
    """Run synchronous routing and its HTTP-backed Supervisor off the event loop."""
    return await asyncio.to_thread(resolve_voice_route, **kwargs)
