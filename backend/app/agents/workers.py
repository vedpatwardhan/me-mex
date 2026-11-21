"""Headless worker handlers — LLM via `get_chains().*.invoke()` only."""

from __future__ import annotations

import json
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.agents.context_preprocessor import apply_custom_fields_to_text
from app.agents.source_reference import resolve_source_reference
from app.config import settings
from app.db import Store, ToolContext
from app.llm import get_chains
from app.llm.budget import passage_chunk_size_chars
from app.llm.schemas import WorkerRoute
from app.services.decision_scorer import ScorerNode, get_decision_scorer
from app.services.decision_trace_context import decision_trace_scope
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


def route_intent(text: str, context: dict, project: Any) -> WorkerRoute:
    fields = context.get("custom_fields") or {}
    if fields.get("resume_job_id"):
        return WorkerRoute(worker="conversation", intent="status", dispatch=False)
    if fields.get("force_project_scope") and not (project.introduction or "").strip():
        return WorkerRoute(
            worker="project_scope",
            intent="scope_conversation",
            dispatch=True,
        )
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
    if isinstance(result, WorkerRoute):
        decision = result.model_copy(update={"source_error": None})
    else:
        worker = str(result if isinstance(result, str) else result.worker)
        decision = WorkerRoute(
            worker=worker,
            dispatch=worker not in {"conversation"},
        )

    # A substantive scope proposal is itself the input to the approval workflow.
    # Treat a generated proposal as dispatchable even if the Supervisor forgets
    # to set the dispatch bit; short chit-chat without a candidate stays in Convo.
    scope_candidate = str(decision.content or "").strip()
    if (
        decision.worker == "project_scope"
        and decision.intent == "scope_conversation"
        and len(scope_candidate) >= 100
    ):
        decision = decision.model_copy(update={"dispatch": True})

    needs_source = decision.intent in {"source_summary", "source_analysis"} or (
        decision.intent == "commit_gist" and not (decision.content or fields.get("gist"))
    )
    has_raw_source = bool(str(fields.get("raw_text") or "").strip())
    if needs_source and not (decision.source_reference or decision.source_field or has_raw_source):
        return decision.model_copy(
            update={
                "source_error": "I couldn't identify which supplied source to use. Please select or resend its link."
            }
        )

    source = resolve_source_reference(
        text,
        fields,
        selected_reference=decision.source_reference,
        selected_field=decision.source_field,
    )
    if source.error:
        return decision.model_copy(update={"source_reference": None, "source_error": source.error})
    if source.url:
        return decision.model_copy(update={"source_reference": source.url})
    if needs_source and not has_raw_source:
        return decision.model_copy(
            update={
                "source_error": "The selected source field doesn't contain a readable link or arXiv ID."
            }
        )
    return decision


def conversation_worker(
    ctx: ToolContext,
    text: str,
    *,
    context: dict | None = None,
    gist_draft: str | None = None,
) -> dict:
    if gist_draft:
        return {"reply": gist_draft, "graph_write": False}
    proj = ctx.store.get_project(ctx.project_id)
    effective = apply_custom_fields_to_text(text, context)
    reply = get_chains().conversation.invoke(
        {"text": effective, "project_scope": proj.introduction or ""}
    )
    return {"reply": reply, "graph_write": False}


def gist_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    decision = context.get("supervisor_decision") or {}
    proj = ctx.store.get_project(ctx.project_id)
    source = resolve_source_reference(
        text,
        fields,
        selected_reference=decision.get("source_reference"),
        selected_field=decision.get("source_field"),
    )
    if decision.get("source_error"):
        return {
            "reply": decision["source_error"],
            "source_error": decision["source_error"],
            "graph_write": False,
            "error": True,
        }
    if source.error:
        return {
            "reply": source.error,
            "source_error": source.error,
            "graph_write": False,
            "error": True,
        }

    source_text = str(fields.get("raw_text") or "").strip()
    source_title = str(decision.get("title") or fields.get("title") or "").strip()
    if source.url:
        fetched = fetch_tool.fetch_normalized_text(ctx, source.url)
        source_text = (fetched.get("text") or "").strip()
        if not source_text:
            return {
                "reply": (
                    "I couldn't extract readable text from that source, so I haven't made a "
                    "summary. Please check the link or send the document text."
                ),
                "source_url": source.url,
                "source_error": fetched.get("error") or "empty_document",
                "graph_write": False,
                "error": True,
            }
        source_title = source_title or _document_title(source_text)

    if source_text:
        gist_text = _summarize_source(
            source_text,
            source_title=source_title,
            source_url=source.url or "",
            project_scope=(proj.introduction or "")[:1000],
        )
        if not gist_text:
            return {
                "reply": "I couldn't produce a grounded summary from the extracted source text.",
                "source_url": source.url,
                "source_error": "empty_summary",
                "graph_write": False,
                "error": True,
            }
    else:
        gist_text = ""

    explicit_commit = decision.get("intent") == "commit_gist" or fields.get("force_gist_commit")
    if explicit_commit:
        title = decision.get("title") or fields.get("title") or source_title or "Untitled source"
        gist_text = fields.get("gist") or decision.get("content") or gist_text or text
        out = gist.create_or_update_root_gist(ctx, title=title, gist=gist_text)
        uri = source.url or fields.get("url") or fields.get("arxiv_id")
        if uri and out.get("root_id"):
            gist.attach_source_uri(ctx, root_id=out["root_id"], uri=str(uri))
        return {
            "reply": "ROOT gist saved.",
            "result": out,
            "source_summary": gist_text,
            "source_title": title,
            "source_url": source.url,
            "gist_saved": True,
            "graph_write": True,
        }

    if not gist_text:
        return {
            "reply": "Share a document link or excerpt and I'll summarize that source.",
            "graph_write": False,
            "error": True,
        }
    return {
        "reply": gist_text,
        "source_summary": gist_text,
        "source_title": source_title,
        "source_url": source.url,
        "graph_write": False,
    }


def intradoc_worker(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    decision = context.get("supervisor_decision") or {}
    root_id = fields.get("root_id")
    source = resolve_source_reference(
        text,
        fields,
        selected_reference=decision.get("source_reference"),
        selected_field=decision.get("source_field"),
    )
    if decision.get("source_error"):
        return {
            "reply": decision["source_error"],
            "source_error": decision["source_error"],
            "graph_write": False,
            "error": True,
        }
    if source.error:
        return {
            "reply": source.error,
            "source_error": source.error,
            "graph_write": False,
            "error": True,
        }
    url = source.url
    title = fields.get("title") or "Document"
    doc_text = str(fields.get("raw_text") or "").strip()
    content_hash = ""
    if url:
        fetched = fetch_tool.fetch_normalized_text(ctx, url)
        doc_text = fetched.get("text") or ""
        content_hash = fetched["content_hash"]
        if not doc_text.strip():
            return {
                "reply": (
                    "I couldn't extract readable text from that source, so I haven't staged an "
                    "analysis. Please check the link or send the document text."
                ),
                "source_url": url,
                "source_error": fetched.get("error") or "empty_document",
                "graph_write": False,
                "error": True,
            }
        title = fields.get("title") or _document_title(doc_text) or title
    if not doc_text.strip():
        return {
            "reply": "Share a document link or excerpt and I'll analyze that source.",
            "graph_write": False,
            "error": True,
        }

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
        "source_url": url,
        "graph_write": False,
    }


def _document_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()
    return ""


def _summarize_source(
    text: str,
    *,
    source_title: str,
    source_url: str,
    project_scope: str,
) -> str:
    """Summarize long documents hierarchically within the configured LLM context budget."""
    chain = get_chains().gist_draft
    chunk_size = max(2000, passage_chunk_size_chars())
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=min(300, chunk_size // 10),
    )
    chunks = splitter.split_text(text)

    def summarize(part: str, stage: str) -> str:
        result = chain.invoke(
            {
                "text": part,
                "project_scope": project_scope,
                "source_title": source_title,
                "source_url": source_url,
                "summary_stage": stage,
            }
        )
        return str(result or "").strip()

    if len(chunks) == 1:
        return summarize(chunks[0], "Summarize the complete source document.")

    summaries = [
        summarize(chunk, f"Summarize source excerpt {index + 1} of {len(chunks)}.")
        for index, chunk in enumerate(chunks)
    ]
    summaries = [summary for summary in summaries if summary]
    if not summaries:
        return ""

    while len("\n\n".join(summaries)) > chunk_size:
        groups = splitter.split_text("\n\n".join(summaries))
        summaries = [
            summary
            for summary in (
                summarize(group, "Consolidate these source-derived section summaries.")
                for group in groups
            )
            if summary
        ]
        if len(summaries) <= 1:
            break
    return summarize(
        "\n\n".join(summaries),
        "Synthesize these source-derived section summaries into one concise whole-document gist.",
    )


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
    with decision_trace_scope(ctx, "placement"):
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
    with decision_trace_scope(ctx, "reorg_neighbor"):
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
        with decision_trace_scope(ctx, "retrieval_expand"):
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


def scratch_worker_with_context(ctx: ToolContext, text: str, context: dict) -> dict:
    fields = context.get("custom_fields") or {}
    decision = context.get("supervisor_decision") or {}
    intent = decision.get("intent")
    if intent == "create_note":
        title = str(decision.get("title") or "Note")
        body = str(decision.get("content") or "")
        out = gist.create_note(ctx, title=title, body=body)
        return {"reply": "Note created.", "result": out, "graph_write": True}
    if intent == "create_todo":
        title = str(decision.get("title") or "ToDo")
        body = str(decision.get("content") or "")
        out = gist.create_todo(ctx, title=title, body=body)
        return {"reply": "Todo created.", "result": out, "graph_write": True}
    if intent == "promote_todo":
        todo_id = fields.get("promote_todo_id") or decision.get("target_id")
        if not todo_id:
            return {"reply": "Select the ToDo you want to promote.", "graph_write": False}
        out = gist.promote_todo_to_concept_m(ctx, todo_id=str(todo_id))
        return {"reply": "Todo promoted.", "result": out, "graph_write": True}
    return {
        "reply": "I couldn't determine which note or ToDo action you want.",
        "graph_write": False,
    }


def project_scope_worker(ctx: ToolContext, text: str, context: dict | None = None) -> dict:
    from app.agents.scope_proposal import (
        load_scope_proposal,
        record_scope_turn,
        update_scope_proposal,
        upsert_project_scope_approval,
    )

    proj = ctx.store.get_project(ctx.project_id)
    context = context or {}
    approval_id = context.get("approval_id")
    decision = context.get("supervisor_decision") or {}
    fields = context.get("custom_fields") or {}

    if decision.get("intent") == "scope_save":
        draft = load_scope_proposal(ctx.thread_id)
        intro = str(decision.get("content") or draft.get("proposed_introduction") or "").strip()
        if not intro:
            recorded = record_scope_turn(ctx.thread_id, text)
            response = get_chains().project_scope.invoke(
                {
                    "payload": json.dumps(
                        {
                            "current_scope": (proj.introduction or "").strip(),
                            "latest_user_message": text,
                            "draft_proposal": recorded.get("proposed_introduction", ""),
                            "conversation_turns": recorded.get("conversation_turns", []),
                        },
                        ensure_ascii=False,
                    )
                }
            )
            intro = str(response or "").strip()
        if not intro:
            return {
                "reply": "I don't have a complete scope proposal to save yet. Tell me what to revise.",
                "graph_write": False,
            }
        update_scope_proposal(ctx.thread_id, intro)
        if fields.get("force_scope_commit") and not context.get("voice_dispatch"):
            project.update_project_scope(ctx, introduction=intro)
            return {"reply": "Scope saved.", "graph_write": True}
        aid = upsert_project_scope_approval(
            ctx,
            proposed_introduction=intro,
            approval_id=str(approval_id) if approval_id else None,
            title="Review project scope (save requested)",
        )
        return {
            "reply": "Scope proposal is in the dock—approve when ready.",
            "graph_write": False,
            "approval_id": aid,
            "proposal_preview": intro[:400],
        }

    committed = (proj.introduction or "").strip()
    draft = record_scope_turn(ctx.thread_id, text)
    reply = get_chains().project_scope.invoke(
        {
            "payload": json.dumps(
                {
                    "current_scope": committed,
                    "latest_user_message": text,
                    "draft_proposal": draft.get("proposed_introduction", ""),
                    "conversation_turns": draft.get("conversation_turns", []),
                },
                ensure_ascii=False,
            ),
        }
    )
    proposed = str(reply or "").strip()
    if not proposed:
        proposed = draft.get("proposed_introduction") or text.strip()
    update_scope_proposal(ctx.thread_id, proposed)
    summary = "Project scope proposal updated. Review it in the dock."
    aid = upsert_project_scope_approval(
        ctx,
        proposed_introduction=proposed,
        approval_id=str(approval_id) if approval_id else None,
        title="Review project scope",
    )
    return {
        "reply": summary,
        "graph_write": False,
        "approval_id": aid,
        "proposal_preview": proposed[:400],
        "progress": summary,
    }
