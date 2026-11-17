"""Minimal LangGraph headless turn (Phase 1)."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from app.agents import workers
from app.db import ToolContext, get_store
from app.services.checkpoints import JsonCheckpointStore


class AgentState(TypedDict, total=False):
    text: str
    context_json: dict
    project_id: str
    thread_id: str
    worker: str
    output: dict


def _supervisor(state: AgentState) -> AgentState:
    ctx = ToolContext(
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        store=get_store(),
    )
    project = ctx.store.get_project(ctx.project_id)
    worker = workers.route_intent(
        state["text"], state.get("context_json") or {}, project
    )
    return {**state, "worker": worker}


def _worker_node(state: AgentState) -> AgentState:
    ctx = ToolContext(
        project_id=state["project_id"],
        thread_id=state["thread_id"],
        store=get_store(),
    )
    text = state["text"]
    context = state.get("context_json") or {}
    w = state.get("worker", "conversation")
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
        out = workers.project_scope_worker(ctx, text)
    elif w == "scratch":
        out = workers.scratch_worker_with_context(ctx, text, context)
    else:
        out = workers.conversation_worker(ctx, text)
    return {**state, "output": out}


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("supervisor", _supervisor)
    g.add_node("worker", _worker_node)
    g.set_entry_point("supervisor")
    g.add_edge("supervisor", "worker")
    g.add_edge("worker", END)
    return g.compile()


_compiled = None


def run_agent_turn(
    *,
    store,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict | None = None,
    checkpointer: JsonCheckpointStore | None = None,
) -> dict:
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    state: AgentState = {
        "text": text,
        "context_json": context_json or {},
        "project_id": project_id,
        "thread_id": thread_id,
    }
    result = _compiled.invoke(state)
    out = result.get("output") or {}
    if checkpointer:
        checkpointer.save(
            thread_id,
            {"last_worker": result.get("worker"), "last_output": out},
        )
    return {
        "worker": result.get("worker"),
        "reply": out.get("reply", ""),
        "graph_write": out.get("graph_write", False),
        "details": out,
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
    from app.tools import dock, gist, link, reorg, staging

    ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
    item = store.resolve_approval(approval_id, action)
    if action != "approve":
        return {"status": "dismissed", "approval_id": approval_id}
    payload = item.payload
    if item.approval_type == "placement":
        root_id = payload["root_id"]
        targets = [c[0] for c in payload.get("candidates", [])[:2]]
        link.create_root_insight_edges(ctx, root_id=root_id, target_ids=targets)
        return {"status": "approved", "edges": targets}
    if item.approval_type == "intra_doc_staging":
        root_id = (context_json or {}).get("custom_fields", {}).get(
            "root_id"
        ) or payload.get("root_id")
        staging_key = payload.get("staging_key")
        if not root_id:
            bundle = store.get_staging(staging_key)
            root_id = bundle.root_id
        if not root_id:
            raise ValueError("root_id required to commit staging")
        return staging.commit_intra_doc_graph(
            ctx, staging_key=staging_key, root_id=root_id
        )
    if item.approval_type == "reorg":
        return reorg.apply_reorg_plan(ctx, proposal_id=payload["proposal_id"])
    return {"status": "approved", "approval_id": approval_id}
