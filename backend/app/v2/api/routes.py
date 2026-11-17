from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.v2.agents.graph import resume_approval, run_agent_turn
from app.v2.db import ToolContext, get_store
from app.v2.models import AgentResumeRequest, AgentTurnRequest
from app.v2.services.checkpoints import JsonCheckpointStore
from app.v2.tools import reorg as reorg_tools

router = APIRouter(prefix="/api/v2", tags=["v2"])
_checkpoints = JsonCheckpointStore()


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


@router.post("/agent/turn")
def agent_turn(body: AgentTurnRequest):
    store = get_store()
    project_id = body.context_json.get("active_project_id") or body.context_json.get(
        "project_id"
    )
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


@router.post("/agent/resume")
def agent_resume(body: AgentResumeRequest):
    store = get_store()
    project_id = body.context_json.get("active_project_id") or body.context_json.get(
        "project_id"
    )
    if not project_id:
        raise HTTPException(400, "active_project_id required")
    try:
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


@router.delete("/graph/nodes/{node_id}")
def delete_node(project_id: str, node_id: str):
    store = get_store()
    ctx = ToolContext(project_id=project_id, thread_id="ui", store=store)
    return reorg_tools.delete_node(ctx, node_id=node_id)


@router.get("/graph/highlights/{thread_id}")
def get_highlights(thread_id: str):
    return {"node_ids": get_store().get_highlight_ids(thread_id)}
