import uuid
from typing import Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.models import (
    ProjectWorkspace,
    ChatMessageRecord,
)
from app.agents.orchestrator import orchestrator
from app.db import db_engine

app = FastAPI(title="Me-Mex (me-mex) Backend Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class ChatRequest(BaseModel):
    query: str
    project_id: str = "global"
    is_voice: bool = False
    chat_history: List[Dict[str, str]] = []


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Unified Orchestrated Chat Endpoint: Classifies intent, streams events, and collects traversal/tool evidence."""
    final_reply = ""
    intent = "CONVERSATION"
    department_findings = []
    touched_nodes = []
    tool_calls = []
    events_log = []

    # Persist user chat message
    user_msg = ChatMessageRecord(
        _id=f"msg_user_{uuid.uuid4().hex[:8]}",
        project_id=req.project_id,
        sender="user",
        text=req.query,
        is_voice=req.is_voice,
    )
    db_engine.upsert_message(user_msg)

    async for event in orchestrator.process_user_message(
        req.query, req.chat_history, project_id=req.project_id
    ):
        evt_type = event.get("event")
        events_log.append(event)

        if evt_type == "intent_classified":
            intent = event.get("intent", "CONVERSATION")
        elif evt_type == "node_touched":
            touched_nodes.append(
                {
                    "node_id": event.get("node_id"),
                    "node_title": event.get("node_title"),
                    "persona_id": event.get("persona_id"),
                    "persona_name": event.get("persona_name"),
                }
            )
        elif evt_type == "orchestrator_tool_call":
            tool_calls.append(
                {
                    "tool_name": event.get("tool_name"),
                    "args": event.get("args"),
                }
            )
        elif evt_type == "chat_complete":
            final_reply = event.get("final_answer", "")
            department_findings = event.get("department_findings", [])
        elif evt_type == "tool_complete":
            final_reply = event.get("message", "")

    if not final_reply:
        final_reply = f"Processed {req.query}."

    # Persist agent reply
    agent_msg = ChatMessageRecord(
        _id=f"msg_agent_{uuid.uuid4().hex[:8]}",
        project_id=req.project_id,
        sender="agent",
        text=final_reply,
        grounded_node_ids=[t["node_id"] for t in touched_nodes if t.get("node_id")],
    )
    db_engine.upsert_message(agent_msg)

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
def get_graph(project_id: str = "global"):
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


# --- Project Workspaces ---
@app.get("/api/projects")
def get_projects():
    projects = db_engine.get_projects()
    return [p.model_dump(by_alias=True) for p in projects]


@app.get("/api/projects/{project_id}/chat")
def get_project_chat(project_id: str):
    """Retrieve project-isolated chat history."""
    messages = db_engine.get_chat_history(project_id)
    return [m.model_dump(by_alias=True) for m in messages]


@app.post("/api/projects")
def create_project(project: ProjectWorkspace):
    db_engine.upsert_project(project)
    return {"status": "created", "project": project.model_dump(by_alias=True)}


if __name__ == "__main__":
    import uvicorn
    from app.config import settings

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
