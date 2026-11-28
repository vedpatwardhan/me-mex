"""LangGraph agent turn (Phase 1 headless + Phase 2 interactive primitives)."""

from __future__ import annotations

import logging
import operator
import os
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents import job_runtime, workers
from app.agents.context_preprocessor import (
    apply_custom_fields_to_text,
    block_graph_writes_without_scope,
    graph_candidates_for_supervisor,
    prioritize_project_scope_until_complete,
)
from app.agents.jobs import job_from_worker_turn
from app.agents.turn_dispatch import normalize_link_decision
from app.db import ToolContext, get_store
from app.services.checkpoints import JsonCheckpointStore

_checkpointer = MemorySaver()
_log = logging.getLogger("memex.v2.graph")


class AgentState(TypedDict, total=False):
    text: str
    effective_text: str
    context_json: dict
    project_id: str
    thread_id: str
    worker: str
    supervisor_decision: dict
    output: dict
    jobs: Annotated[list[dict[str, Any]], operator.add]
    scope_blocked: bool


def _supervisor(state: AgentState) -> AgentState:
    """Custom fields, P1 scope gate, and supervisor chain routing (04 §8)."""
    ctx = ToolContext(
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        store=get_store(),
    )
    project = ctx.store.get_project(ctx.project_id)
    effective = apply_custom_fields_to_text(state["text"], state.get("context_json") or {})
    context = dict(state.get("context_json") or {})
    from app.agents.session_plane import build_routing_memory

    context["routing_memory"] = build_routing_memory(state["thread_id"])
    context["graph_candidates"] = graph_candidates_for_supervisor(ctx.store, ctx.project_id)
    context["scope_approval_pending"] = any(
        item.approval_type == "project_scope"
        for item in ctx.store.list_pending(ctx.project_id, ctx.thread_id)
    )
    decision = workers.route_intent(effective, context, project)
    worker = prioritize_project_scope_until_complete(project.introduction, decision.worker, context)
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
    decision = normalize_link_decision(decision, context, utterance=effective)
    if decision.dispatch and decision.worker in {"gist", "intradoc"}:
        from app.agents.session_plane import record_routing_source
        from app.agents.source_reference import resolve_source_reference

        fields = context.get("custom_fields") or {}
        source = resolve_source_reference(
            effective,
            fields,
            selected_reference=decision.source_reference,
            selected_field=decision.source_field,
        )
        record_routing_source(
            state["thread_id"],
            worker=decision.worker,
            source_url=source.url,
            title=decision.title or fields.get("title"),
            root_id=fields.get("root_id"),
        )
    return {
        **state,
        "context_json": context,
        "effective_text": effective,
        "worker": worker,
        "supervisor_decision": decision.model_dump(),
        "scope_blocked": scope_blocked,
    }


def _worker_node(state: AgentState) -> AgentState:
    ctx = ToolContext(
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        store=get_store(),
    )
    text = state.get("effective_text") or state["text"]
    context = dict(state.get("context_json") or {})
    context["supervisor_decision"] = state.get("supervisor_decision") or {}
    w = state.get("worker", "conversation")
    fields = context.get("custom_fields") or {}
    resume_job_id = fields.get("resume_job_id")
    if resume_job_id:
        job = job_runtime.resume_job(str(resume_job_id))
        if job and job.get("output"):
            return {**state, "output": job["output"], "worker": "intradoc"}
    bg_intradoc = (
        fields.get("background_intradoc") == "1"
        or float(os.getenv("INTRADOC_BG_SLEEP_S", "0") or 0) > 0
    )
    if w == "intradoc" and bg_intradoc:
        job = job_runtime.start_background_intradoc(
            thread_id=state["thread_id"],
            ctx=ctx,
            text=text,
            context=context,
            worker_fn=workers.intradoc_worker,
        )
        return {
            **state,
            "output": {
                "reply": f"Deep read started in background (job {job['job_id']}).",
                "graph_write": False,
                "job_id": job["job_id"],
            },
            "worker": "intradoc",
        }
    if state.get("scope_blocked"):
        out = {
            "reply": "Set project scope first (unmute / P1 onboarding) before graph writes.",
            "graph_write": False,
        }
        return {**state, "output": out}

    if w == "gist":
        out = workers.gist_worker(ctx, text, context)
    elif w == "intradoc":
        out = workers.intradoc_worker(ctx, text, context)
    elif w == "link":
        out = workers.link_place_worker(ctx, context)
    elif w == "reorg":
        out = workers.reorg_recommend_worker(ctx)
    elif w == "retrieval":
        out = workers.retrieval_worker(ctx, text, context)
    elif w == "project_scope":
        out = workers.project_scope_worker(ctx, text, context=context)
    elif w == "scratch":
        out = workers.scratch_worker_with_context(ctx, text, context)
    elif w == "job_control":
        out = workers.job_control_worker(ctx, text, context)
    else:
        out = workers.conversation_worker(ctx, text, context=context)
    return {**state, "output": out}


def _hitl_gate(state: AgentState) -> AgentState:
    out = state.get("output") or {}
    approval_id = out.get("approval_id")
    if not approval_id:
        return state
    from langgraph.types import interrupt

    decision = interrupt(
        {
            "type": "approval",
            "approval_id": approval_id,
            "title": out.get("reply") or "Pending approval",
            "preview": out,
        }
    )
    action = "dismiss"
    if isinstance(decision, dict):
        action = decision.get("action", "dismiss")
    if action != "approve":
        from app.services.hitl_traces import log_hitl_action

        log_hitl_action(
            action="dismiss",
            approval_id=approval_id,
            thread_id=state["thread_id"],
            project_id=state["project_id"],
            approval_type=None,
        )
        return {**state, "output": {**out, "graph_write": False, "status": "dismissed"}}
    store = get_store()
    result = resume_approval(
        store=store,
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        approval_id=approval_id,
        action="approve",
        context_json=state.get("context_json"),
    )
    return {
        **state,
        "output": {**out, **result, "graph_write": True, "status": "approved"},
    }


def _workflow_observer(state: AgentState) -> AgentState:
    out = state.get("output") or {}
    w = state.get("worker", "conversation")
    if w == "job_control":
        return {**state, "jobs": []}
    job = job_from_worker_turn(w, state.get("text", ""), out)
    return {**state, "jobs": [job]}


def build_graph(*, checkpointer=None):
    g = StateGraph(AgentState)
    g.add_node("supervisor", _supervisor)
    g.add_node("worker", _worker_node)
    g.add_node("hitl_gate", _hitl_gate)
    g.add_node("observer", _workflow_observer)
    g.set_entry_point("supervisor")
    g.add_edge("supervisor", "worker")
    g.add_edge("worker", "observer")
    g.add_edge("observer", "hitl_gate")
    g.add_edge("hitl_gate", END)
    cp = checkpointer if checkpointer is not None else _checkpointer
    return g.compile(checkpointer=cp)


_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


def run_agent_turn(
    *,
    store,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict | None = None,
    checkpointer: JsonCheckpointStore | None = None,
) -> dict:
    graph = get_compiled_graph()
    state: AgentState = {
        "text": text,
        "context_json": context_json or {},
        "project_id": project_id,
        "thread_id": thread_id,
        "jobs": [],
    }
    config = {"configurable": {"thread_id": thread_id}}
    graph.invoke(state, config=config)
    snap = graph.get_state(config)
    values = snap.values if snap and snap.values else {}
    out = values.get("output") or {}
    jobs = list(values.get("jobs") or []) + job_runtime.list_jobs(thread_id)
    if checkpointer:
        checkpoint_state = checkpointer.load(thread_id) or {}
        checkpoint_state.update(
            {
                "last_worker": values.get("worker"),
                "last_output": out,
                "jobs": jobs,
            }
        )
        checkpointer.save(thread_id, checkpoint_state)
    return {
        "worker": values.get("worker"),
        "reply": out.get("reply", ""),
        "graph_write": out.get("graph_write", False),
        "details": out,
        "jobs": jobs,
    }


def resume_approval(
    *,
    store,
    project_id: str,
    thread_id: str,
    approval_id: str,
    action: str,
    context_json: dict | None = None,
) -> dict:
    from app.services.hitl_traces import append_hitl_label_trace, log_hitl_action
    from app.tools import gist, link, project, reorg, staging

    ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
    item = store.resolve_approval(approval_id, action)
    log_hitl_action(
        action=action,
        approval_id=approval_id,
        thread_id=thread_id,
        project_id=project_id,
        approval_type=item.approval_type,
    )
    if action != "approve":
        job_runtime.resolve_approval_job(thread_id, approval_id, action)
        return {
            "status": "dismissed",
            "approval_id": approval_id,
            "approval_type": item.approval_type,
            "graph_write": False,
            "reply": _approval_reply(item.approval_type, item.title, {}, action="dismiss"),
        }

    def _resolved(result: dict) -> dict:
        job_runtime.resolve_approval_job(thread_id, approval_id, action)
        from app.agents.session_plane import record_recent_graph_change

        record_recent_graph_change(
            store=store,
            project_id=project_id,
            thread_id=thread_id,
            operation=item.approval_type,
            payload=item.payload,
            result=result,
        )
        result.setdefault("status", "approved")
        result.setdefault("approval_id", approval_id)
        result.setdefault("approval_type", item.approval_type)
        result.setdefault("graph_write", True)
        result["reply"] = result.get("reply") or _approval_reply(
            item.approval_type,
            item.title,
            result,
        )
        return result

    payload = item.payload
    if item.approval_type == "placement":
        root_id = payload["root_id"]
        targets = [c[0] for c in payload.get("candidates", [])[:2]]
        append_hitl_label_trace(ctx, item, chosen_ids=targets)
        edge_result = link.create_root_insight_edges(ctx, root_id=root_id, target_ids=targets)
        turn_id = (context_json or {}).get("turn_id")
        if turn_id:
            from app.agents.turn_journal import append_turn_effect

            eids = edge_result.get("edge_ids") or []
            append_turn_effect(
                thread_id,
                turn_id=str(turn_id),
                kind="placement_edges",
                forward={"root_id": root_id, "edge_ids": eids},
                inverse={"edge_ids": eids},
            )
        return _resolved({"status": "approved", "edges": targets})
    if item.approval_type == "intra_doc_staging":
        staging_key = payload.get("staging_key")
        bundle = store.get_staging(staging_key)
        root_id = (
            (context_json or {}).get("custom_fields", {}).get("root_id")
            or payload.get("root_id")
            or bundle.root_id
        )
        if root_id:
            root = store.get_node(str(root_id))
            if root.project_id != project_id or root.node_kind.value != "ROOT":
                raise ValueError("Intra-doc commit requires a ROOT in the active project")
        elif bundle.pending_url:
            existing_root = next(
                (
                    node
                    for node in store.list_nodes(project_id)
                    if node.node_kind.value == "ROOT" and node.source_uri == bundle.pending_url
                ),
                None,
            )
            if existing_root:
                root_id = existing_root.id
            else:
                created = gist.create_or_update_root_gist(
                    ctx,
                    title=bundle.source_title or "Untitled source",
                    gist=bundle.doc_description,
                )
                root_id = created["root_id"]
                gist.attach_source_uri(ctx, root_id=root_id, uri=bundle.pending_url)
        else:
            created = gist.create_or_update_root_gist(
                ctx,
                title=bundle.source_title or "Untitled source",
                gist=bundle.doc_description,
            )
            root_id = created["root_id"]
        bundle.root_id = str(root_id)
        store.upsert_staging(staging_key, bundle)
        return _resolved(
            staging.commit_intra_doc_graph(ctx, staging_key=staging_key, root_id=str(root_id))
        )
    if item.approval_type == "reorg":
        append_hitl_label_trace(ctx, item)
        return _resolved(reorg.apply_reorg_plan(ctx, proposal_id=payload["proposal_id"]))
    if item.approval_type == "gist_root":
        created = gist.create_or_update_root_gist(
            ctx,
            title=payload.get("title", "Untitled"),
            gist=payload.get("gist", ""),
        )
        source_uri = payload.get("source_uri")
        if created.get("root_id") and source_uri:
            gist.attach_source_uri(ctx, root_id=created["root_id"], uri=str(source_uri))
        turn_id = (context_json or {}).get("turn_id")
        if turn_id and created.get("root_id"):
            from app.agents.turn_journal import append_turn_effect

            append_turn_effect(
                thread_id,
                turn_id=str(turn_id),
                kind="gist_root",
                forward={"root_id": created["root_id"]},
                inverse={"root_id": created["root_id"]},
            )
        return _resolved({"status": "approved", "approval_id": approval_id, "result": created})
    if item.approval_type == "project_scope":
        intro = payload.get("proposed_introduction") or payload.get("introduction") or ""
        prev_intro = (store.get_project(project_id).introduction or "") if store else ""
        turn_id = (context_json or {}).get("turn_id")
        project.update_project_scope(ctx, introduction=str(intro))
        if turn_id:
            from app.agents.turn_journal import append_turn_effect

            append_turn_effect(
                thread_id,
                turn_id=str(turn_id),
                kind="project_scope",
                forward={"introduction": str(intro)},
                inverse={"previous_introduction": prev_intro},
            )
        job_runtime.resolve_approval_job(thread_id, approval_id, action)
        return {
            "status": "approved",
            "approval_id": approval_id,
            "approval_type": item.approval_type,
            "scope_committed": True,
            "graph_write": True,
            "reply": _scope_approval_reply(str(intro)),
        }
    return _resolved({"status": "approved", "approval_id": approval_id})


def _scope_approval_reply(introduction: str) -> str:
    from app.agents.conversation_utterance import (
        EMERGENCY_FALLBACK,
        SCOPE_APPROVAL_EMERGENCY,
        UtteranceIntent,
        build_conversation_turn,
        invoke_conversation_utterance,
    )

    inp = build_conversation_turn(
        intent=UtteranceIntent.APPROVAL_ACK,
        user_message="The user approved the project scope.",
        briefing={},
        project_scope=introduction,
        utterance_facts={"approval_type": "project_scope", "action": "approve"},
    )
    try:
        text = invoke_conversation_utterance(inp, intent=UtteranceIntent.APPROVAL_ACK)
        if text and text != EMERGENCY_FALLBACK and "scope" in text.lower():
            return text
    except Exception:  # noqa: BLE001 - scope is committed before optional acknowledgement generation
        _log.exception("Scope approval acknowledgement generation failed")
    return SCOPE_APPROVAL_EMERGENCY


def _approval_reply(
    approval_type: str,
    title: str,
    result: dict,
    *,
    action: str = "approve",
) -> str:
    from app.agents.conversation_utterance import (
        EMERGENCY_FALLBACK,
        UtteranceIntent,
        build_conversation_turn,
        invoke_conversation_utterance,
    )

    inp = build_conversation_turn(
        intent=UtteranceIntent.APPROVAL_ACK,
        user_message=f"The user {action}d a pending change.",
        briefing={},
        project_scope="",
        utterance_facts={
            "approval_type": approval_type,
            "title": title,
            "action": action,
            "result": {k: v for k, v in result.items() if k in {"status", "graph_write"}},
        },
    )
    try:
        reply = invoke_conversation_utterance(inp, intent=UtteranceIntent.APPROVAL_ACK)
        if reply and reply.casefold().strip(".! ") not in {"approved", "done", "success"}:
            return reply
    except Exception:  # noqa: BLE001 - graph write has completed; retain a natural fallback
        _log.exception("Approval acknowledgement generation failed for %s", approval_type)
    return EMERGENCY_FALLBACK


async def astream_agent_turn(
    *,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict | None = None,
):
    """Yield dock SSE payloads from astream_events v3."""
    from app.agents.streaming import event_to_dock_payload
    from app.agents.turn_dispatch import is_dock_turn

    voice = is_dock_turn(context_json)
    graph = get_compiled_graph()
    state: AgentState = {
        "text": text,
        "context_json": context_json or {},
        "project_id": project_id,
        "thread_id": thread_id,
        "jobs": [],
    }
    config = {"configurable": {"thread_id": thread_id}}
    event_iter = await graph.astream_events(state, config=config, version="v3")
    async for ev in event_iter:
        payload = event_to_dock_payload(ev, dock_turn=voice)
        if payload:
            yield payload
    snap = await graph.aget_state(config)
    values = snap.values if snap else {}
    out = values.get("output") or {}
    yield {
        "type": "turn_end",
        "worker": values.get("worker"),
        "reply": out.get("reply", ""),
        "graph_write": out.get("graph_write", False),
        "details": out,
        "jobs": list(values.get("jobs") or []) + job_runtime.list_jobs(thread_id),
    }
