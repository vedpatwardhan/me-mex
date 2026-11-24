from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents import job_runtime
from app.agents.conversation_voice import astream_conversation_voice
from app.agents.graph import (
    astream_agent_turn,
    get_compiled_graph,
    resume_approval,
    run_agent_turn,
)
from app.agents.session_events import format_sse, subscribe_session_events
from app.agents.session_plane import build_session_briefing, list_job_history
from app.agents.turn_journal import list_turn_journal, register_abort, revert_turn
from app.db import ToolContext, get_store
from app.models import (
    AgentResumeRequest,
    AgentTurnRequest,
    NodeKind,
    TurnAbortRequest,
    TurnRevertRequest,
)
from app.services.checkpoints import JsonCheckpointStore
from app.tools import dock as dock_tools
from app.tools import reorg as reorg_tools

router = APIRouter(prefix="/api", tags=["api"])
_checkpoints = JsonCheckpointStore()


def _ts_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _project_to_workspace(doc: dict) -> dict:
    ts = doc.get("created_at", 0)
    return {
        "id": doc["_id"],
        "name": doc.get("name", ""),
        "description": doc.get("introduction") or doc.get("description", ""),
        "node_ids": doc.get("node_ids") or [],
        "edge_ids": doc.get("edge_ids") or [],
        "created_at": _ts_iso(ts) if ts else datetime.now(tz=UTC).isoformat(),
    }


def _node_to_frontend(n) -> dict:
    d = n.model_dump(by_alias=True)
    d["id"] = n.id
    d["node_type"] = "ROOT" if n.node_kind == NodeKind.ROOT else "concept"
    d["project_ids"] = [n.project_id]
    d["created_at"] = _ts_iso(n.created_at)
    d["updated_at"] = _ts_iso(n.updated_at)
    if n.node_kind == NodeKind.CONCEPT_I:
        d["is_immutable"] = True
    return d


def _edge_to_frontend(e) -> dict:
    return {
        "id": e.id,
        "source": e.source_id,
        "target": e.target_id,
        "source_node_id": e.source_id,
        "target_node_id": e.target_id,
        "weight": 1.0,
        "project_ids": [e.project_id],
        "created_at": _ts_iso(e.created_at),
    }


@router.get("/projects")
def list_projects():
    store = get_store()
    return [_project_to_workspace(doc) for doc in store.list_projects()]


@router.get("/graph")
def get_project_graph(project_id: str = Query(..., min_length=1)):
    store = get_store()
    nodes = [_node_to_frontend(n) for n in store.list_nodes(project_id)]
    edges = [_edge_to_frontend(e) for e in store.list_edges(project_id)]
    return {"nodes": nodes, "edges": edges}


@router.post("/projects")
def create_project(name: str = Query(..., min_length=1)):
    store = get_store()
    project = store.create_project(name=name)
    return {
        "project_id": project.id,
        "name": project.name,
        "genesis_node_id": project.genesis_node_id,
    }


@router.get("/projects/{project_id}/nodes")
def list_project_nodes(project_id: str):
    store = get_store()
    nodes = store.list_nodes(project_id)
    return {"nodes": [n.model_dump(by_alias=True) for n in nodes]}


@router.get("/graph/nodes/{node_id}")
def get_node(node_id: str):
    store = get_store()
    try:
        n = store.get_node(node_id)
    except Exception as e:
        raise HTTPException(404, str(e)) from e
    return n.model_dump(by_alias=True)


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    store = get_store()
    try:
        p = store.get_project(project_id)
    except Exception as e:
        raise HTTPException(404, str(e)) from e
    return p.model_dump(by_alias=True)


@router.get("/agent/session/briefing")
def session_briefing(
    project_id: str = Query(..., min_length=1),
    thread_id: str = Query(..., min_length=1),
):
    return build_session_briefing(project_id=project_id, thread_id=thread_id)


@router.get("/agent/session/events")
async def session_events(
    project_id: str = Query(..., min_length=1),
    thread_id: str = Query(..., min_length=1),
):
    async def gen():
        async for event in subscribe_session_events(thread_id):
            yield format_sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/voice/conversation/stream")
async def voice_conversation_stream(body: AgentTurnRequest):
    project_id = body.context_json.get("active_project_id") or body.context_json.get("project_id")
    if not project_id:
        raise HTTPException(400, "active_project_id required in context_json")
    ctx = {**body.context_json, "voice_turn": True}

    async def gen():
        async for chunk in astream_conversation_voice(
            project_id=project_id,
            thread_id=body.thread_id,
            text=body.text,
            context_json=ctx,
        ):
            import json

            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agent/turn/stream")
async def agent_turn_stream(body: AgentTurnRequest):
    project_id = body.context_json.get("active_project_id") or body.context_json.get("project_id")
    if not project_id:
        raise HTTPException(400, "active_project_id required in context_json")

    async def gen():
        async for chunk in astream_agent_turn(
            project_id=project_id,
            thread_id=body.thread_id,
            text=body.text,
            context_json=body.context_json,
        ):
            import json

            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/agent/turn")
def agent_turn(body: AgentTurnRequest):
    store = get_store()
    project_id = body.context_json.get("active_project_id") or body.context_json.get("project_id")
    if not project_id:
        raise HTTPException(400, "active_project_id required in context_json")
    return run_agent_turn(
        store=store,
        project_id=project_id,
        thread_id=body.thread_id,
        text=body.text,
        context_json=body.context_json,
        checkpointer=_checkpoints,
    )


@router.get("/agent/approvals")
def list_approvals(
    project_id: str,
    thread_id: str | None = None,
):
    store = get_store()
    ctx = ToolContext(project_id=project_id, thread_id=thread_id or "ui", store=store)
    return dock_tools.list_pending_approvals(ctx)


@router.get("/agent/jobs")
def list_agent_jobs(project_id: str, thread_id: str):
    return {
        "items": [
            job
            for job in job_runtime.list_jobs(thread_id)
            if job.get("project_id") == project_id
            and job.get("approval_resolution") not in {"approve", "dismiss"}
        ]
    }


@router.post("/agent/jobs/{job_id}/{action}")
def control_agent_job(
    job_id: str,
    action: Literal["pause", "resume", "cancel", "delete"],
    project_id: str,
    thread_id: str,
):
    try:
        return job_runtime.control_job(
            thread_id,
            job_id,
            action,
            project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/agent/nudges")
def list_nudges(project_id: str):
    store = get_store()
    ctx = ToolContext(project_id=project_id, thread_id="ui", store=store)
    return dock_tools.get_suggested_next_actions(ctx)


@router.post("/agent/resume")
def agent_resume(body: AgentResumeRequest):
    store = get_store()
    project_id = body.context_json.get("active_project_id") or body.context_json.get("project_id")
    if not project_id:
        raise HTTPException(400, "active_project_id required")
    try:
        graph = get_compiled_graph()
        config = {"configurable": {"thread_id": body.thread_id}}
        snap = graph.get_state(config)
        if snap.next:
            from langgraph.types import Command

            result = graph.invoke(
                Command(
                    resume={
                        "action": body.action,
                        "approval_id": body.approval_id,
                    }
                ),
                config=config,
            )
            out = (result or {}).get("output") or {}
            payload = {
                "status": out.get("status", "resumed"),
                "graph_write": out.get("graph_write", False),
            }
            for key in (
                "concept_ids",
                "edges",
                "approval_id",
                "root_id",
                "reply",
                "approval_type",
                "scope_committed",
            ):
                if key in out:
                    payload[key] = out[key]
            return payload
        return resume_approval(
            store=store,
            project_id=project_id,
            thread_id=body.thread_id,
            approval_id=body.approval_id,
            action=body.action,
            context_json=body.context_json,
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@router.post("/voice/conversation/abort")
def voice_conversation_abort(body: TurnAbortRequest):
    register_abort(body.turn_id)
    return {"status": "aborted", "turn_id": body.turn_id}


@router.post("/agent/turn/revert")
def agent_turn_revert(body: TurnRevertRequest):
    store = get_store()
    try:
        return revert_turn(
            thread_id=body.thread_id,
            turn_id=body.turn_id,
            store=store,
            project_id=body.project_id,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/agent/jobs/history")
def agent_jobs_history(thread_id: str = Query(..., min_length=1)):
    items = list_job_history(thread_id)
    return {"items": list(reversed(items))}


@router.get("/agent/turns")
def agent_turns(thread_id: str = Query(..., min_length=1)):
    return {"items": list_turn_journal(thread_id)}


@router.delete("/graph/nodes/{node_id}")
def delete_node(project_id: str, node_id: str):
    store = get_store()
    ctx = ToolContext(project_id=project_id, thread_id="ui", store=store)
    return reorg_tools.delete_node(ctx, node_id=node_id)


@router.get("/graph/highlights/{thread_id}")
def get_highlights(thread_id: str):
    return {"node_ids": get_store().get_highlight_ids(thread_id)}
