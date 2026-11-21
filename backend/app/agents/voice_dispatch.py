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
    text: str,
    context_json: dict[str, Any],
) -> tuple[WorkerRoute, str, bool]:
    from app.agents.context_preprocessor import (
        apply_custom_fields_to_text,
        block_graph_writes_without_scope,
        prioritize_project_scope_until_complete,
    )
    from app.agents.workers import route_intent

    project = store.get_project(project_id)
    effective = apply_custom_fields_to_text(text, context_json or {})
    decision = route_intent(effective, context_json or {}, project)
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
