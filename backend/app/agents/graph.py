"""LangGraph agent turn (Phase 1 headless + Phase 2 interactive primitives)."""

from __future__ import annotations

import operator
import os
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents import job_runtime, workers
from app.agents.context_preprocessor import (
    apply_custom_fields_to_text,
    block_graph_writes_without_scope,
    prioritize_project_scope_until_complete,
)
from app.agents.jobs import job_from_worker_turn
from app.db import ToolContext, get_store
from app.services.checkpoints import JsonCheckpointStore

_checkpointer = MemorySaver()


class AgentState(TypedDict, total=False):
    text: str
    effective_text: str
    context_json: dict
    project_id: str
    thread_id: str
    worker: str
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
    context = state.get("context_json") or {}
    worker = workers.route_intent(effective, context, project)
    worker = prioritize_project_scope_until_complete(project.introduction, worker, context)
    scope_blocked = block_graph_writes_without_scope(project.introduction, worker)
    if scope_blocked:
        worker = "project_scope"
    return {
        **state,
        "effective_text": effective,
        "worker": worker,
        "scope_blocked": scope_blocked,
    }


def _worker_node(state: AgentState) -> AgentState:
    ctx = ToolContext(
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        store=get_store(),
    )
    text = state.get("effective_text") or state["text"]
    context = state.get("context_json") or {}
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
    job_runtime.park_active_jobs(thread_id)
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
        return {"status": "dismissed", "approval_id": approval_id}
    payload = item.payload
    if item.approval_type == "placement":
        root_id = payload["root_id"]
        targets = [c[0] for c in payload.get("candidates", [])[:2]]
        append_hitl_label_trace(ctx, item, chosen_ids=targets)
        link.create_root_insight_edges(ctx, root_id=root_id, target_ids=targets)
        return {"status": "approved", "edges": targets}
    if item.approval_type == "intra_doc_staging":
        root_id = (context_json or {}).get("custom_fields", {}).get("root_id") or payload.get(
            "root_id"
        )
        staging_key = payload.get("staging_key")
        if not root_id:
            bundle = store.get_staging(staging_key)
            root_id = bundle.root_id
        if not root_id:
            raise ValueError("root_id required to commit staging")
        return staging.commit_intra_doc_graph(ctx, staging_key=staging_key, root_id=root_id)
    if item.approval_type == "reorg":
        append_hitl_label_trace(ctx, item)
        return reorg.apply_reorg_plan(ctx, proposal_id=payload["proposal_id"])
    if item.approval_type == "gist_root":
        gist.create_or_update_root_gist(
            ctx,
            title=payload.get("title", "Untitled"),
            gist=payload.get("gist", ""),
        )
        return {"status": "approved", "approval_id": approval_id}
    if item.approval_type == "project_scope":
        intro = payload.get("proposed_introduction") or payload.get("introduction") or ""
        project.update_project_scope(ctx, introduction=str(intro))
        return {"status": "approved", "approval_id": approval_id, "graph_write": True}
    return {"status": "approved", "approval_id": approval_id}


async def astream_agent_turn(
    *,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict | None = None,
):
    """Yield dock SSE payloads from astream_events v3."""
    from app.agents.streaming import event_to_dock_payload
    from app.agents.voice_dispatch import is_voice_turn

    voice = is_voice_turn(context_json)
    for job in job_runtime.park_active_jobs(thread_id):
        yield {"type": "custom", "job": job}

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
        payload = event_to_dock_payload(ev, voice_turn=voice)
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
