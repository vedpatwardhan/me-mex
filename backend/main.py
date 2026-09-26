import asyncio
import random
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from app.models import (
    AgentProposal,
    GraphEdge,
    GraphNode,
    IntakeRequest,
    ProjectWorkspace,
    ReportRequest,
    ReportResponse,
)

from app.api.sse import router as sse_router
from app.db import db_engine

app = FastAPI(title="Me-Mex (me-mex) Backend Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sse_router)


@app.get("/")
def read_root():
    nodes = db_engine.get_nodes()
    edges = db_engine.get_edges()
    return {
        "status": "online",
        "system": "Me-Mex (me-mex) Engine",
        "nodes_count": len(nodes),
        "edges_count": len(edges),
    }


from pydantic import BaseModel
from app.agents.orchestrator import orchestrator


class ChatRequest(BaseModel):
    query: str
    project_id: Optional[str] = "global"
    is_voice: Optional[bool] = False
    chat_history: Optional[List[Dict[str, str]]] = None


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Unified Orchestrated Chat Endpoint: Classifies intent, streams events, and collects traversal/tool evidence."""
    final_reply = ""
    intent = "DIRECT_CONVERSATION"
    department_findings = []
    touched_nodes = []
    tool_calls = []
    events_log = []

    async for event in orchestrator.process_user_message(req.query, req.chat_history):
        evt_type = event.get("event")
        events_log.append(event)

        if evt_type == "intent_classified":
            intent = event.get("intent", "DIRECT_CONVERSATION")
        elif evt_type == "node_touched":
            touched_nodes.append({
                "node_id": event.get("node_id"),
                "node_title": event.get("node_title"),
                "persona_id": event.get("persona_id"),
                "persona_name": event.get("persona_name"),
            })
        elif evt_type == "orchestrator_tool_call":
            tool_calls.append({
                "tool_name": event.get("tool_name"),
                "args": event.get("args"),
            })
        elif evt_type == "chat_complete":
            final_reply = event.get("final_answer", "")
            department_findings = event.get("department_findings", [])
        elif evt_type == "tool_complete":
            final_reply = event.get("message", "")

    if not final_reply:
        final_reply = f"Processed {req.query}."

    return {
        "reply": final_reply,
        "intent": intent,
        "department_findings": department_findings,
        "touched_nodes": touched_nodes,
        "tool_calls": tool_calls,
        "events": events_log,
        "status": "success",
    }


# --- Graph Nodes & Edges Endpoints ---
@app.get("/api/graph")
def get_graph(project_id: Optional[str] = "global"):
    """Fetch nodes and edges filtered by project_id. 'global' returns master superset."""
    nodes = db_engine.get_nodes(project_id)
    edges = db_engine.get_edges(project_id)

    return {
        "project_id": project_id,
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
    }


@app.get("/api/nodes/{node_id}")
def get_node(node_id: str):
    node = db_engine.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    edges = db_engine.get_edges()
    outgoing = [e.model_dump() for e in edges if e.source_id == node_id]
    incoming = [e.model_dump() for e in edges if e.target_id == node_id]

    return {
        "node": node.model_dump(),
        "outgoing_edges": outgoing,
        "incoming_edges": incoming,
    }


@app.post("/api/nodes")
def create_node(node: GraphNode):
    """Create a new node. Enforces Superset Rule: node is added to Global Graph first."""
    if "global" not in node.project_ids:
        node.project_ids.append("global")

    db_engine.upsert_node(node)
    return {"status": "created", "node": node.model_dump()}


@app.post("/api/edges")
def create_edge(edge: GraphEdge):
    """Create a new edge between nodes."""
    if not db_engine.get_node(edge.source_id) or not db_engine.get_node(edge.target_id):
        raise HTTPException(status_code=400, detail="Invalid source or target node ID")

    if "global" not in edge.project_ids:
        edge.project_ids.append("global")

    db_engine.upsert_edge(edge)
    return {"status": "created", "edge": edge.model_dump()}


# --- Project Workspaces ---
@app.get("/api/projects")
def get_projects():
    return [
        {
            "id": "global",
            "name": "Global Master Graph",
            "description": "Master superset database across all paradigms and literature.",
            "node_ids": [],
            "edge_ids": [],
        }
    ]


@app.post("/api/projects")
def create_project(project: ProjectWorkspace):
    return {"status": "created", "project": project.model_dump()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
