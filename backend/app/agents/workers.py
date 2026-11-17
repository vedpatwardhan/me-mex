"""Headless worker handlers — model calls in agent layer; tools stay deterministic."""

from __future__ import annotations

import uuid
from typing import Any

from app.db import ToolContext
from app.services.chat_llm import get_chat_llm, stub_intradoc_concepts
from app.services.passage_packing import pack_document_passages
from app.services.decision_scorer import ScorerNode, get_decision_scorer
from app.tools import dock, gist, link, project, reorg, staging
from app.tools import fetch as fetch_tool
from app.config import settings


def route_intent(text: str, context: dict, project: Any) -> str:
    return get_chat_llm().classify_worker(text, context, project)


def conversation_worker(
    ctx: ToolContext, text: str, *, gist_draft: str | None = None
) -> dict:
    project = ctx.store.get_project(ctx.project_id)
    reply = get_chat_llm().conversation_reply(
        text, project=project, gist_draft=gist_draft
    )
    return {"reply": reply, "graph_write": False}


def gist_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    project = ctx.store.get_project(ctx.project_id)
    if "create root" in text.lower() or fields.get("force_gist_commit"):
        title = fields.get("title") or "Untitled source"
        gist_text = fields.get("gist") or text
        out = gist.create_or_update_root_gist(ctx, title=title, gist=gist_text)
        uri = fields.get("url") or fields.get("arxiv_id")
        if uri and out.get("root_id"):
            gist.attach_source_uri(ctx, root_id=out["root_id"], uri=str(uri))
        return {"reply": "ROOT gist saved.", "result": out, "graph_write": True}
    draft = get_chat_llm().gist_draft(text, project=project)
    return conversation_worker(ctx, text, gist_draft=draft)


def run_intradoc_extract(
    *,
    text: str,
    doc_title: str,
    user_intent: str,
) -> list[dict[str, Any]]:
    """Pack passages → per-passage extract → consolidate (stub or live via get_chat_llm)."""
    chat = get_chat_llm()
    passages = pack_document_passages(text) if text.strip() else [""]
    raw = [
        chat.extract_passage(
            p,
            doc_title=doc_title,
            passage_index=i,
            user_intent=user_intent,
        )
        for i, p in enumerate(passages)
    ]
    consolidated = chat.consolidate_extractions(
        raw,
        doc_title=doc_title,
        user_intent=user_intent,
    )
    out: list[dict[str, Any]] = []
    for i, c in enumerate(consolidated.concepts):
        out.append(
            {
                "concept_id": f"c{i + 1}_{uuid.uuid4().hex[:6]}",
                "title": c.title,
                "description": c.description,
            }
        )
    return out or stub_intradoc_concepts()


def intradoc_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    root_id = fields.get("root_id")
    url = fields.get("url")
    title = fields.get("title") or "Document"
    doc_text = ""
    content_hash = ""
    if url:
        fetched = fetch_tool.fetch_normalized_text(ctx, url)
        doc_text = fetched.get("text") or ""
        content_hash = fetched["content_hash"]
    if not doc_text.strip():
        doc_text = fields.get("raw_text") or text

    concepts = run_intradoc_extract(
        text=doc_text,
        doc_title=title,
        user_intent=text,
    )
    key_out = staging.upsert_staging_bundle(
        ctx,
        root_id=root_id,
        pending_url=url,
        concepts=concepts,
        content_hash=content_hash,
    )
    approval_id = dock.enqueue_pending_approval(
        ctx,
        approval_type="intra_doc_staging",
        title="Review intra-doc staging",
        payload=key_out,
    )
    return {
        "reply": "Staging ready for review.",
        "approval_id": approval_id,
        "graph_write": False,
    }


def link_place_worker(ctx: ToolContext, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    root_id = fields.get("root_id")
    if not root_id:
        return {"reply": "Need root_id in custom_fields.", "graph_write": False}
    nodes = ctx.store.list_nodes(ctx.project_id)
    frontier = [n for n in nodes if n.id != root_id][:10]
    query = ScorerNode(id=root_id, title=root_id, node_kind="ROOT")
    front = [
        ScorerNode(id=n.id, title=n.title, node_kind=n.node_kind.value)
        for n in frontier
    ]
    probs = get_decision_scorer().score(query, front)
    ranked = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    approval_id = dock.enqueue_pending_approval(
        ctx,
        approval_type="placement",
        title="Connect ROOT?",
        payload={"root_id": root_id, "candidates": ranked[:5]},
    )
    return {
        "reply": "Placement options in dock.",
        "approval_id": approval_id,
        "graph_write": False,
    }


def reorg_recommend_worker(ctx: ToolContext) -> dict:
    nodes = ctx.store.list_nodes(ctx.project_id)
    crowded = [n for n in nodes if ctx.store.degree(n.id) > settings.DEGREE_THRESHOLD]
    if not crowded:
        return {"reply": "No crowded hubs.", "graph_write": False}
    hub = crowded[0]
    neighbor_ids = ctx.store.neighbors(hub.id)[:12]
    if not neighbor_ids:
        return {"reply": "Hub has no neighbors to score.", "graph_write": False}
    by_id = {n.id: n for n in nodes}
    query = ScorerNode(
        id=hub.id, title=hub.title, node_kind=hub.node_kind.value, gist=hub.description
    )
    front = [
        ScorerNode(
            id=nid,
            title=by_id[nid].title,
            node_kind=by_id[nid].node_kind.value,
            gist=by_id[nid].description,
        )
        for nid in neighbor_ids
        if nid in by_id
    ]
    probs = get_decision_scorer().score(query, front)
    ranked = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:5]
    prop = reorg.write_reorg_proposal(
        ctx,
        proposal={
            "before": {"hub_id": hub.id},
            "after": {"split": True},
            "moves": [
                {"node_id": nid, "parent_id": hub.id, "score": s} for nid, s in ranked
            ],
            "scores": ranked,
        },
    )
    preview = reorg.preview_reorg_diff(ctx, proposal_id=prop["proposal_id"])
    approval_id = dock.enqueue_pending_approval(
        ctx,
        approval_type="reorg",
        title=f"Reorganize {hub.title}?",
        payload=preview,
    )
    return {
        "reply": "Reorg preview ready.",
        "approval_id": approval_id,
        "graph_write": False,
    }


def retrieval_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    seed = (
        fields.get("query_node_id") or (context.get("selected_node_ids") or [None])[0]
    )
    if not seed:
        nodes = ctx.store.list_nodes(ctx.project_id)
        seed = nodes[0].id if nodes else None
    if not seed:
        return {"reply": "Graph empty.", "graph_write": False}

    project = ctx.store.get_project(ctx.project_id)
    scorer = get_decision_scorer()
    visited = {seed}
    expand: list[str] = []
    current = seed
    max_depth = settings.MAX_TRAVERSAL_DEPTH
    top_k = max(1, settings.RETRIEVAL_TRAVERSAL_TOP_K)

    for _ in range(max_depth):
        neighbor_ids = [n for n in ctx.store.neighbors(current) if n not in visited]
        if not neighbor_ids:
            break
        query = ScorerNode(id=current, title=current, node_kind="CONCEPT_M")
        front = [
            ScorerNode(id=nid, title=nid, node_kind="CONCEPT_M") for nid in neighbor_ids
        ]
        probs = scorer.score(query, front)
        hop = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:top_k]
        for nid, _ in hop:
            if nid not in visited:
                visited.add(nid)
                expand.append(nid)
        if not hop:
            break
        current = hop[0][0]

    link.highlight_nodes(ctx, node_ids=expand + [seed])
    summary = get_chat_llm().retrieval_summary(
        query=text, highlighted_ids=expand, project=project
    )
    return {
        "reply": summary,
        "graph_write": False,
        "highlight": expand,
    }


def scratch_worker(ctx: ToolContext, text: str) -> dict:
    t = text.lower()
    if "create note" in t or "add note" in t:
        title = text.split(":", 1)[-1].strip() if ":" in text else "Note"
        out = gist.create_note(ctx, title=title, body="")
        return {"reply": "Note created.", "result": out, "graph_write": True}
    if "create todo" in t or "add todo" in t:
        title = text.split(":", 1)[-1].strip() if ":" in text else "Todo"
        out = gist.create_todo(ctx, title=title, body="")
        return {"reply": "Todo created.", "result": out, "graph_write": True}
    if "promote todo" in t:
        return {"reply": "Set todo_id in custom_fields.", "graph_write": False}
    return conversation_worker(ctx, text)


def scratch_worker_with_context(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    if fields.get("promote_todo_id"):
        out = gist.promote_todo_to_concept_m(ctx, todo_id=fields["promote_todo_id"])
        return {"reply": "Todo promoted.", "result": out, "graph_write": True}
    return scratch_worker(ctx, text)


def project_scope_worker(ctx: ToolContext, text: str) -> dict:
    proj = ctx.store.get_project(ctx.project_id)
    if "update_project_scope" in text or "save scope" in text.lower():
        intro = text.split(":", 1)[-1].strip() if ":" in text else text
        project.update_project_scope(ctx, introduction=intro)
        return {"reply": "Scope saved.", "graph_write": True}
    reply = get_chat_llm().project_scope_reply(text, project=proj)
    return {"reply": reply, "graph_write": False}
