import asyncio
import random
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from database import db
from models import (
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
    return {
        "status": "online",
        "system": "Me-Mex (me-mex) Engine",
        "nodes_count": len(db.nodes),
        "edges_count": len(db.edges),
        "projects_count": len(db.projects),
    }


# --- Graph Nodes & Edges Endpoints ---
@app.get("/api/graph")
def get_graph(project_id: Optional[str] = "global"):
    """Fetch nodes and edges filtered by project_id. 'global' returns master superset."""
    if project_id and project_id != "global" and project_id in db.projects:
        proj = db.projects[project_id]
        nodes = [db.nodes[nid] for nid in proj.node_ids if nid in db.nodes]
        edges = [db.edges[eid] for eid in proj.edge_ids if eid in db.edges]
    else:
        nodes = list(db.nodes.values())
        edges = list(db.edges.values())

    return {
        "project_id": project_id,
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
    }


@app.get("/api/nodes/{node_id}")
def get_node(node_id: str):
    if node_id not in db.nodes:
        raise HTTPException(status_code=404, detail="Node not found")
    node = db.nodes[node_id]

    # Calculate incoming and outgoing connections
    outgoing = [
        e.model_dump() for e in db.edges.values() if e.source_node_id == node_id
    ]
    incoming = [
        e.model_dump() for e in db.edges.values() if e.target_node_id == node_id
    ]

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

    db.nodes[node.id] = node

    # Reflect into target project workspaces
    for pid in node.project_ids:
        if pid in db.projects and node.id not in db.projects[pid].node_ids:
            db.projects[pid].node_ids.append(node.id)

    return {"status": "created", "node": node.model_dump()}


@app.post("/api/edges")
def create_edge(edge: GraphEdge):
    """Create a new edge between nodes."""
    if edge.source_node_id not in db.nodes or edge.target_node_id not in db.nodes:
        raise HTTPException(status_code=400, detail="Invalid source or target node ID")

    if "global" not in edge.project_ids:
        edge.project_ids.append("global")

    db.edges[edge.id] = edge

    for pid in edge.project_ids:
        if pid in db.projects and edge.id not in db.projects[pid].edge_ids:
            db.projects[pid].edge_ids.append(edge.id)

    return {"status": "created", "edge": edge.model_dump()}


# --- Project Workspaces ---
@app.get("/api/projects")
def get_projects():
    return list(db.projects.values())


@app.post("/api/projects")
def create_project(project: ProjectWorkspace):
    db.projects[project.id] = project
    return {"status": "created", "project": project.model_dump()}


# --- Ingestion Pipeline ---
@app.post("/api/intake")
def intake_content(req: IntakeRequest, background_tasks: BackgroundTasks):
    """Bi-directional Seeded Ingestion Endpoint (URL printer, PDF, Voice note, Text)."""
    new_doc_id = f"doc_{int(time.time())}"
    new_node_id = f"node_{int(time.time())}"

    node_type = "post"
    if req.source_type == "voice" or req.source_type == "text":
        node_type = "post"
    elif req.source_type == "url":
        if (
            "arxiv.org" in req.content_or_url.lower()
            or "paper" in req.content_or_url.lower()
        ):
            node_type = "paper"
        elif (
            "youtube.com" in req.content_or_url.lower()
            or "youtu.be" in req.content_or_url.lower()
        ):
            node_type = "video"
        else:
            node_type = "blog"

    title = (
        req.title_hint
        or f"Ingested {req.source_type.upper()}: {req.content_or_url[:30]}..."
    )

    new_node = GraphNode(
        id=new_node_id,
        node_type=node_type,
        title=title,
        takeaway_2line=f"Bi-directionally extracted concept from {req.source_type} stream.",
        content=f"# {title}\n\nProcessed content from intake stream:\n\n{req.content_or_url}",
        project_ids=["global", req.project_id]
        if req.project_id != "global"
        else ["global"],
        metadata={"source_type": req.source_type, "input": req.content_or_url},
    )

    db.nodes[new_node_id] = new_node
    if req.project_id in db.projects:
        db.projects[req.project_id].node_ids.append(new_node_id)

    # Generate seed edge connection to an existing relevant node
    existing_node_ids = list(db.nodes.keys())
    if len(existing_node_ids) > 1:
        target_id = random.choice(
            [nid for nid in existing_node_ids if nid != new_node_id]
        )
        edge_id = f"edge_{int(time.time())}"
        seed_edge = GraphEdge(
            id=edge_id,
            source_node_id=new_node_id,
            target_node_id=target_id,
            is_directional=True,
            text_body="Bi-directional seeded trajectory match",
            provenance_quote="Bi-directional seeded trajectory match",
            project_ids=["global", req.project_id],
        )
        db.edges[edge_id] = seed_edge

    return {
        "status": "ingested",
        "node": new_node.model_dump(),
        "seed_traversal": [new_node_id, target_id]
        if len(existing_node_ids) > 1
        else [new_node_id],
    }


# --- Agent Proposals ---
@app.get("/api/proposals")
def get_proposals():
    return list(db.proposals.values())


@app.post("/api/proposals/{proposal_id}/action")
def proposal_action(proposal_id: str, action: str):
    if proposal_id not in db.proposals:
        raise HTTPException(status_code=404, detail="Proposal not found")
    prop = db.proposals[proposal_id]

    if action == "accept":
        prop.status = "accepted"
        if prop.proposal_type == "link" and prop.source_node_id and prop.target_node_id:
            edge_id = f"edge_prop_{int(time.time())}"
            new_edge = GraphEdge(
                id=edge_id,
                source_node_id=prop.source_node_id,
                target_node_id=prop.target_node_id,
                is_directional=True,
                text_body=prop.description or "Accepted agent proposal link",
                provenance_quote=prop.description,
                project_ids=["global"],
            )
            db.edges[edge_id] = new_edge
    elif action == "reject":
        prop.status = "rejected"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    return {"status": prop.status, "proposal": prop.model_dump()}


# --- Interactive Node-Grounded Report Studio ---
@app.post("/api/reports/generate", response_model=ReportResponse)
def generate_report(req: ReportRequest):
    """Generates an interactive markdown report with node-provenance highlight mappings."""
    report_id = f"rep_{int(time.time())}"

    selected_nodes = [db.nodes[nid] for nid in req.target_node_ids if nid in db.nodes]
    if not selected_nodes:
        selected_nodes = list(db.nodes.values())[:4]

    md_lines = [
        f"# Research Report: {req.title}\n",
        f"**Generated Scope:** {req.project_id} workspace | **Node Count:** {len(selected_nodes)}\n",
        "---",
        "## 1. Executive Synthesis\n",
    ]

    provenance_map = {}

    for idx, node in enumerate(selected_nodes):
        phrase = f"Key Finding {idx+1}: {node.takeaway_2line}"
        provenance_map[phrase] = node.id

        node_color_tag = "blue"
        if node.node_type == "human_insight":
            node_color_tag = "yellow"
        elif node.node_type == "agent_hypothesis":
            node_color_tag = "purple"
        elif node.node_type == "concept_phrase":
            node_color_tag = "cyan"

        md_lines.append(f"### 1.{idx+1} {node.title}\n")
        md_lines.append(
            f'<span class="provenance-highlight tag-{node_color_tag}" data-node-id="{node.id}">{phrase}</span>\n'
        )
        md_lines.append(
            f"**Node Type:** `{node.node_type}` | **Source:** [`{node.id}`]\n"
        )
        md_lines.append(f"{node.content[:300]}...\n")

    full_md = "\n".join(md_lines)

    rep = ReportResponse(
        id=report_id,
        title=req.title,
        markdown_content=full_md,
        provenance_mappings=provenance_map,
    )
    db.reports[report_id] = rep
    return rep


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
