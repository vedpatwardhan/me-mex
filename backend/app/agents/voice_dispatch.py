"""Voice dispatch policy (04 §12.11, plan phase 0)."""

from __future__ import annotations

from typing import Any

VOICE_DIALOGUE_ONLY_WORKERS = frozenset({"conversation", "scratch"})

VOICE_DISPATCH_WORKERS = frozenset(
    {
        "gist",
        "intradoc",
        "link",
        "reorg",
        "retrieval",
        "project_scope",
    }
)


def is_voice_turn(context_json: dict[str, Any] | None) -> bool:
    if not context_json:
        return False
    if context_json.get("voice_turn") is True:
        return True
    return str(context_json.get("voice_turn", "")).lower() in ("1", "true", "yes")


def needs_voice_dispatch(
    worker_kind: str,
    *,
    voice_turn: bool,
    text: str = "",
    scope_blocked: bool = False,
) -> bool:
    if not voice_turn:
        return False
    if scope_blocked or worker_kind in VOICE_DIALOGUE_ONLY_WORKERS:
        return False
    if worker_kind == "project_scope":
        return True
    return worker_kind in VOICE_DISPATCH_WORKERS or worker_kind not in VOICE_DIALOGUE_ONLY_WORKERS


def resolve_voice_route(
    *,
    store,
    project_id: str,
    text: str,
    context_json: dict[str, Any],
) -> tuple[str, str, bool]:
    from app.agents.context_preprocessor import (
        apply_custom_fields_to_text,
        block_graph_writes_without_scope,
        prioritize_project_scope_until_complete,
    )
    from app.agents.workers import route_intent

    project = store.get_project(project_id)
    effective = apply_custom_fields_to_text(text, context_json or {})
    worker = route_intent(effective, context_json or {}, project)
    worker = prioritize_project_scope_until_complete(project.introduction, worker, context_json)
    scope_blocked = block_graph_writes_without_scope(project.introduction, worker)
    if scope_blocked:
        worker = "project_scope"
    return worker, effective, scope_blocked
