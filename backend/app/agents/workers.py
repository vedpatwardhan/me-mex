"""Headless worker handlers — LLM via `get_chains().*.invoke()` only."""

from __future__ import annotations

import json
from typing import Any

from app.config import settings
from app.db import Store, ToolContext
from app.llm import get_chains
from app.services.decision_scorer import ScorerNode, get_decision_scorer
from app.tools import dock, gist, link, project, reorg, staging
from app.tools import fetch as fetch_tool


def _scorer_node(store: Store, node_id: str) -> ScorerNode:
    node = store.get_node(node_id)
    return ScorerNode(
        id=node.id,
        title=node.title,
        node_kind=node.node_kind.value,
        gist=node.description or "",
        description=node.description or "",
    )


def route_intent(text: str, context: dict, project: Any) -> str:
    fields = context.get("custom_fields") or {}
    if fields.get("resume_job_id"):
        return "conversation"
    if fields.get("force_project_scope") and not (project.introduction or "").strip():
        return "project_scope"
    intro = (project.introduction or "").strip()
    payload = json.dumps({"text": text, "context": context}, ensure_ascii=False)
    result = get_chains().supervisor.invoke(
        {
            "text": text,
            "context": context,
            "project_scope": intro if intro else "(empty)",
            "introduction": intro,
            "payload": payload,
        }
    )
    return result if isinstance(result, str) else result.worker


def conversation_worker(ctx: ToolContext, text: str, *, gist_draft: str | None = None) -> dict:
    if gist_draft:
        return {"reply": gist_draft, "graph_write": False}
    proj = ctx.store.get_project(ctx.project_id)
    reply = get_chains().conversation.invoke(
        {"text": text, "project_scope": proj.introduction or ""}
    )
    return {"reply": reply, "graph_write": False}


def gist_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    proj = ctx.store.get_project(ctx.project_id)
    if "create root" in text.lower() or fields.get("force_gist_commit"):
        title = fields.get("title") or "Untitled source"
        gist_text = fields.get("gist") or text
        out = gist.create_or_update_root_gist(ctx, title=title, gist=gist_text)
        uri = fields.get("url") or fields.get("arxiv_id")
        if uri and out.get("root_id"):
            gist.attach_source_uri(ctx, root_id=out["root_id"], uri=str(uri))
        return {"reply": "ROOT gist saved.", "result": out, "graph_write": True}
    draft = get_chains().gist_draft.invoke({"text": text, "project_scope": proj.introduction or ""})
    return conversation_worker(ctx, text, gist_draft=draft)


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

    concepts = get_chains().intradoc.invoke(
        {"text": doc_text, "doc_title": title, "user_intent": text}
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
    query = _scorer_node(ctx.store, root_id)
    front = [
        ScorerNode(
            id=n.id,
            title=n.title,
            node_kind=n.node_kind.value,
            description=n.description or "",
        )
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
        id=hub.id,
        title=hub.title,
        node_kind=hub.node_kind.value,
        gist=hub.description or "",
        description=hub.description or "",
    )
    front = [
        ScorerNode(
            id=nid,
            title=by_id[nid].title,
            node_kind=by_id[nid].node_kind.value,
            gist=by_id[nid].description or "",
            description=by_id[nid].description or "",
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
            "moves": [{"node_id": nid, "parent_id": hub.id, "score": s} for nid, s in ranked],
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
    seed = fields.get("query_node_id") or (context.get("selected_node_ids") or [None])[0]
    if not seed:
        proj_seed = ctx.store.get_project(ctx.project_id)
        seed = proj_seed.genesis_node_id or None
    if not seed:
        return {"reply": "Graph empty.", "graph_write": False}

    proj = ctx.store.get_project(ctx.project_id)
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
        query = _scorer_node(ctx.store, current)
        front = [_scorer_node(ctx.store, nid) for nid in neighbor_ids]
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
    summary = get_chains().retrieval_summary.invoke(
        {
            "project_scope": proj.introduction or "",
            "payload": (
                f"User asked: {text}\n"
                f"Related node ids: {', '.join(expand[:8])}\n"
                "Brief summary; no graph writes."
            ),
        }
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
    reply = get_chains().project_scope.invoke(
        {
            "payload": json.dumps(
                {
                    "current_scope": proj.introduction or "",
                    "user_message": text,
                }
            ),
        }
    )
    return {"reply": reply, "graph_write": False}
