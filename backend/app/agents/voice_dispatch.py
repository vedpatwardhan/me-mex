"""Voice dispatch policy (04 §12.11, plan phase 0)."""

from __future__ import annotations

import asyncio
import re
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


def _valid_root_id(candidates: dict[str, dict[str, Any]], node_id: str | None) -> str | None:
    if not node_id:
        return None
    node_key = str(node_id)
    if candidates.get(node_key, {}).get("node_kind") == "ROOT":
        return node_key
    return None


def _root_ids_in_target_list(
    target_ids: list[str] | None,
    candidates: dict[str, dict[str, Any]],
) -> list[str]:
    roots: list[str] = []
    for raw_id in target_ids or []:
        node_id = str(raw_id)
        if candidates.get(node_id, {}).get("node_kind") == "ROOT":
            roots.append(node_id)
    return roots


def _swap_recover_root_id(
    decision: WorkerRoute,
    candidates: dict[str, dict[str, Any]],
) -> str | None:
    roots_in_targets = _root_ids_in_target_list(decision.target_ids, candidates)
    if len(roots_in_targets) == 1:
        return roots_in_targets[0]
    explicit = _valid_root_id(candidates, decision.root_id)
    if explicit:
        return None
    if decision.root_id and len(roots_in_targets) == 1:
        return roots_in_targets[0]
    return None


def _utterance_matched_root_ids(
    utterance: str | None,
    candidates: dict[str, dict[str, Any]],
) -> list[str]:
    if not utterance:
        return []
    text = utterance.lower()
    tokens = [token for token in re.findall(r"[a-z0-9]{3,}", text)]
    if not tokens:
        return []
    matched: list[str] = []
    for node_id, node in candidates.items():
        if node.get("node_kind") != "ROOT":
            continue
        title = (node.get("title") or "").lower()
        for token in tokens:
            if token in title:
                matched.append(node_id)
                break
    return list(dict.fromkeys(matched))


def _resolve_link_root_id(
    decision: WorkerRoute,
    *,
    candidates: dict[str, dict[str, Any]],
    fields: dict[str, Any],
    selected_ids: list[str],
    current_source: dict[str, Any],
    focus_root: dict[str, Any],
    utterance: str | None,
) -> str | None:
    root_id = _valid_root_id(candidates, fields.get("root_id"))
    if root_id:
        return root_id

    root_id = _valid_root_id(candidates, decision.root_id)
    if root_id:
        return root_id

    selected_roots = [
        node_id
        for node_id in selected_ids
        if candidates.get(node_id, {}).get("node_kind") == "ROOT"
    ]
    if len(selected_roots) == 1:
        return selected_roots[0]

    current_root_id = _valid_root_id(candidates, current_source.get("root_id"))
    if current_root_id:
        return current_root_id

    swap_root = _swap_recover_root_id(decision, candidates)
    if swap_root:
        return swap_root

    utterance_roots = _utterance_matched_root_ids(utterance, candidates)
    if len(utterance_roots) == 1:
        return utterance_roots[0]

    unrooted_current = bool(current_source and not current_source.get("root_id"))
    if not unrooted_current:
        focus_root_id = _valid_root_id(candidates, focus_root.get("id"))
        if focus_root_id:
            return focus_root_id

        graph_roots = [
            node_id for node_id, node in candidates.items() if node.get("node_kind") == "ROOT"
        ]
        if len(graph_roots) == 1:
            return graph_roots[0]

    return None


def _link_clarification_message(
    candidates: dict[str, dict[str, Any]],
    current_source: dict[str, Any],
    utterance_roots: list[str],
) -> str:
    if len(utterance_roots) > 1:
        titles = [
            str(candidates[node_id].get("title") or node_id) for node_id in utterance_roots[:5]
        ]
        joined = ", ".join(titles)
        return (
            f"More than one paper ROOT matches what you said ({joined}). "
            "Which one should I connect?"
        )

    roots = [
        str(node.get("title") or node_id)
        for node_id, node in candidates.items()
        if node.get("node_kind") == "ROOT"
    ]
    if roots:
        available = ", ".join(roots[:5])
        clarification = f"Which paper ROOT should I connect? Available ROOTs: {available}."
    else:
        clarification = "Which paper ROOT should I connect, and which graph node should it link to?"

    if current_source and not current_source.get("root_id"):
        in_flight = (current_source.get("title") or "").strip()
        if not in_flight:
            in_flight = "The source currently being summarized"
        clarification += (
            f" Note: {in_flight} does not have a ROOT in the graph yet; "
            "you can still connect an existing ROOT from the list."
        )
    return clarification


def _build_link_target_ids(
    decision: WorkerRoute,
    *,
    candidates: dict[str, dict[str, Any]],
    root_id: str,
    selected_ids: list[str],
) -> list[str]:
    target_ids: list[str] = []
    if decision.root_id:
        misplaced = candidates.get(str(decision.root_id))
        if (
            misplaced
            and misplaced.get("node_kind") not in {"ROOT", "CONCEPT_I"}
            and str(decision.root_id) != root_id
        ):
            target_ids.append(str(decision.root_id))
    for target_id in decision.target_ids or []:
        node_id = str(target_id)
        node = candidates.get(node_id)
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
    return list(dict.fromkeys(target_ids))


def normalize_link_decision(
    decision: WorkerRoute,
    context: dict[str, Any],
    *,
    utterance: str | None = None,
) -> WorkerRoute:
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

    utterance_roots = _utterance_matched_root_ids(utterance, candidates)
    root_id = _resolve_link_root_id(
        decision,
        candidates=candidates,
        fields=fields,
        selected_ids=selected_ids,
        current_source=current_source,
        focus_root=focus_root,
        utterance=utterance,
    )

    target_ids = _build_link_target_ids(
        decision,
        candidates=candidates,
        root_id=root_id or "",
        selected_ids=selected_ids,
    )

    if root_id:
        return decision.model_copy(update={"root_id": root_id, "target_ids": target_ids})

    clarification = _link_clarification_message(candidates, current_source, utterance_roots)
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
    decision = normalize_link_decision(decision, routing_context, utterance=effective)
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
