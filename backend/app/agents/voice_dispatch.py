"""Voice dispatch policy (04 §12.11, plan phase 0)."""

from __future__ import annotations

from typing import Any

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
    routing_context["graph_candidates"] = graph_candidates_for_supervisor(store, project_id)
    routing_context["scope_approval_pending"] = any(
        item.approval_type == "project_scope" for item in store.list_pending(project_id, thread_id)
    )
    decision = route_intent(effective, routing_context, project)
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
