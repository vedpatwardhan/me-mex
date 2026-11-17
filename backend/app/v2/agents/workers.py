"""Headless worker handlers (LLM optional; tools deterministic)."""

from __future__ import annotations

from typing import Any

from app.v2.db import ToolContext
from app.v2.models import StagingConcept
from app.v2.services.decision_scorer import ScorerNode, get_decision_scorer
from app.v2.tools import dock, gist, link, project, reorg, staging
from app.v2.tools import fetch as fetch_tool


def conversation_worker(
    ctx: ToolContext, text: str, *, gist_draft: str | None = None
) -> dict:
    """Inquiry / summary — no graph write."""
    return {
        "reply": gist_draft or f"Understood. (No graph write.) You said: {text[:200]}",
        "graph_write": False,
    }


def gist_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    if "create root" in text.lower() or fields.get("force_gist_commit"):
        title = fields.get("title") or "Untitled source"
        gist_text = fields.get("gist") or text
        out = gist.create_or_update_root_gist(ctx, title=title, gist=gist_text)
        uri = fields.get("url") or fields.get("arxiv_id")
        if uri and out.get("root_id"):
            gist.attach_source_uri(ctx, root_id=out["root_id"], uri=str(uri))
        return {"reply": "ROOT gist saved.", "result": out, "graph_write": True}
    return conversation_worker(
        ctx, text, gist_draft="Here's a gist draft in thread only."
    )


def intradoc_worker(ctx: ToolContext, context: dict) -> dict:
    from app.services.llm_tracer import LLMTracer

    LLMTracer().log_call(
        caller="IntraDocWorker.extract_stub",
        model="fixture",
        messages=[{"role": "system", "content": f"project={ctx.project_id}"}],
        duration_seconds=0.0,
        temperature=0.0,
        max_tokens=0,
        response_raw='{"concepts":[{"concept_id":"c1"}]}',
    )
    fields = context.get("custom_fields") or {}
    root_id = fields.get("root_id")
    url = fields.get("url")
    concepts = [
        {
            "concept_id": "c1",
            "title": "Main claim",
            "description": "Extracted stub concept.",
        },
    ]
    content_hash = ""
    if url:
        fetched = fetch_tool.fetch_normalized_text(ctx, url)
        content_hash = fetched["content_hash"]
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
    crowded = [n for n in nodes if ctx.store.degree(n.id) > 7]
    if not crowded:
        return {"reply": "No crowded hubs.", "graph_write": False}
    hub = crowded[0]
    prop = reorg.write_reorg_proposal(
        ctx,
        proposal={
            "before": {"hub_id": hub.id},
            "after": {"split": True},
            "moves": [],
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
    neighbor_ids = ctx.store.neighbors(seed)[:8]
    query = ScorerNode(id=seed, title=seed, node_kind="CONCEPT_M")
    front = [
        ScorerNode(id=nid, title=nid, node_kind="CONCEPT_M") for nid in neighbor_ids
    ]
    probs = get_decision_scorer().score(query, front)
    top = sorted(probs.items(), key=lambda x: x[1], reverse=True)[:3]
    expand = [t[0] for t in top]
    link.highlight_nodes(ctx, node_ids=expand + [seed])
    return {
        "reply": f"Highlighted {len(expand)} related nodes.",
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
    if "update_project_scope" in text or "save scope" in text.lower():
        intro = text.split(":", 1)[-1].strip() if ":" in text else text
        project.update_project_scope(ctx, introduction=intro)
        return {"reply": "Scope saved.", "graph_write": True}
    return {
        "reply": "Tell me what / where / why for this project.",
        "graph_write": False,
    }


def route_intent(text: str, context: dict, project: Any) -> str:
    t = text.lower()
    fields = context.get("custom_fields") or {}
    if "deep read" in t or "intra-doc" in t or "staging" in t:
        return "intradoc"
    if "where does" in t or "connect" in t or "place" in t:
        return "link"
    if "reorg" in t or "split" in t:
        return "reorg"
    if "what relates" in t or "retrieval" in t or "highlight" in t:
        return "retrieval"
    if "create note" in t or "create todo" in t or "promote todo" in t:
        return "scratch"
    if "create root" in t or "save gist" in t or fields.get("force_gist_commit"):
        return "gist"
    if "summarize" in t or ("gist" in t and "?" in t):
        return "conversation"
    if not (project.introduction or "").strip() and (
        "scope" in t or "introduction" in t or t.strip() in ("hello", "hi")
    ):
        return "project_scope"
    if "save scope" in t or "update_project_scope" in t:
        return "project_scope"
    return "conversation"
