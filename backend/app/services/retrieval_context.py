"""Assemble retrieved subgraph context (mutable traversal + immutable evidence closure)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

from app.config import settings
from app.db import db_engine
from app.models import GraphNode, RetrievalRelevancePayload
from app.prompts import load_prompt
from app.services.graph_analytics import MutableTreeIndex
from app.services.ingest_payload import json_dumps_ingest
from app.services.llm_gateway import llm_gateway
from app.services.prompt_mapper import PromptIdMapper


def _node_row(n: GraphNode, *, role: str) -> Dict[str, Any]:
    return {
        "id": n.id,
        "title": n.title,
        "description": n.description,
        "node_type": n.node_type,
        "immutable": n.is_immutable,
        "role": role,
    }


def collect_retrieval_subgraph(
    explored_nodes: List[GraphNode],
    project_id: str,
) -> Dict[str, Any]:
    """
    Post-traversal closure: all explored mutables plus direct immutable neighbors and ROOT provenance.
    """
    tree = MutableTreeIndex(project_id=project_id)
    mutable_nodes: Dict[str, GraphNode] = {}
    for n in explored_nodes:
        if n.is_root_node:
            continue
        if n.is_immutable:
            continue
        mutable_nodes[n.id] = n

    evidence: Dict[str, GraphNode] = {}
    for mid in mutable_nodes:
        for imm in tree.direct_immutable_neighbors(mid):
            evidence[imm.id] = imm

    roots: Dict[str, GraphNode] = {}
    seen_root_ids: Set[str] = set()
    for imm in evidence.values():
        root_id = imm.metadata.get("root_node_id")
        if not root_id or root_id in seen_root_ids:
            continue
        seen_root_ids.add(root_id)
        root = db_engine.get_node(root_id)
        if root and root.is_root_node:
            roots[root_id] = root

    mutable_rows = [_node_row(n, role="mutable_hub") for n in mutable_nodes.values()]
    evidence_rows = [_node_row(n, role="immutable_evidence") for n in evidence.values()]
    root_rows = [_node_row(n, role="root_provenance") for n in roots.values()]

    context_node_ids = sorted(set(mutable_nodes) | set(evidence) | set(roots))

    return {
        "mutable_context_nodes": mutable_rows,
        "immutable_evidence_nodes": evidence_rows,
        "root_provenance_nodes": root_rows,
        "context_node_ids": context_node_ids,
        "context_nodes": list(mutable_nodes.values())
        + list(evidence.values())
        + list(roots.values()),
    }


def build_closure_touch_events(
    closure: Dict[str, Any],
    traversed_node_ids: List[str],
    *,
    persona_id: str,
    persona_name: str,
) -> List[Dict[str, Any]]:
    """SSE node_touched events for immutables/roots added by evidence closure (not yet traversed)."""
    traversed = set(traversed_node_ids)
    root_ids = {
        r.get("id") for r in closure.get("root_provenance_nodes", []) if r.get("id")
    }
    events: List[Dict[str, Any]] = []
    for node in closure.get("context_nodes", []):
        if node.id in traversed:
            continue
        if node.is_root_node:
            role = "root_provenance"
        elif node.is_immutable:
            role = "immutable_evidence"
        else:
            continue
        events.append(
            {
                "event": "node_touched",
                "persona_id": persona_id,
                "persona_name": persona_name,
                "node_id": node.id,
                "node_title": node.title,
                "touch_phase": "evidence_closure",
                "role": role,
                "immutable": node.is_immutable or node.id in root_ids,
                "message": (
                    f"Evidence '{node.title}' linked in retrieval closure ({role})."
                ),
                "timestamp": time.time(),
            }
        )
    events.sort(key=lambda e: e.get("node_id", ""))
    return events


def _rows_for_filter(finding: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, role in (
        ("mutable_context_nodes", "mutable_hub"),
        ("immutable_evidence_nodes", "immutable_evidence"),
        ("root_provenance_nodes", "root_provenance"),
    ):
        for row in finding.get(key, []):
            item = dict(row)
            item.setdefault("role", role)
            rows.append(item)
    return rows


def filter_retrieval_finding_by_relevance(
    query: str,
    finding: Dict[str, Any],
    *,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """LLM pass: shrink explored subgraph to query-relevant nodes before synthesis."""
    if not settings.RETRIEVAL_RELEVANCE_FILTER:
        finding = dict(finding)
        finding.setdefault("answer_scope", "")
        finding["relevance_filter_skipped"] = True
        return finding

    rows = _rows_for_filter(finding)
    if not rows:
        finding = dict(finding)
        finding["answer_scope"] = ""
        return finding

    mapper = PromptIdMapper(prefix="concept")
    indexed: List[Dict[str, Any]] = []
    for row in rows:
        node_id = row.get("id")
        if not node_id:
            continue
        idx = mapper.register(node_id)
        indexed.append(
            {
                "concept_index": idx,
                "title": row.get("title", ""),
                "description": row.get("description", ""),
                "role": row.get("role", ""),
                "immutable": row.get("immutable", False),
            }
        )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": load_prompt("retrieval_relevance_filter")},
    ]
    if chat_history:
        for item in chat_history[-2:]:
            role = "assistant" if item.get("role") in ("agent", "assistant") else "user"
            content = item.get("content") or item.get("text", "")
            messages.append({"role": role, "content": content})
    messages.append(
        {
            "role": "user",
            "content": (
                f'User query: "{query}"\n\n'
                f"Explored candidate concepts ({len(indexed)} items):\n"
                f"{json_dumps_ingest(indexed)}"
            ),
        }
    )

    try:
        payload = llm_gateway.generate_structured_completion(
            messages,
            response_model=RetrievalRelevancePayload,
            temperature=0.1,
            max_tokens=1024,
            max_retries=2,
            enable_reasoning=False,
            caller="ExecutiveOrchestrator.retrieval_relevance_filter",
        )
    except Exception:
        finding = dict(finding)
        finding["answer_scope"] = ""
        finding["relevance_filter_failed"] = True
        return finding

    selected_ids: Set[str] = set()
    for item in payload.selected_concepts:
        nid = mapper.to_id(item.concept_index)
        if nid:
            selected_ids.add(nid)

    if not selected_ids:
        finding = dict(finding)
        finding["answer_scope"] = payload.answer_scope or ""
        finding["relevance_filter_empty"] = True
        return finding

    def _filter_key(key: str) -> List[Dict[str, Any]]:
        return [r for r in finding.get(key, []) if r.get("id") in selected_ids]

    filtered = dict(finding)
    filtered["mutable_context_nodes"] = _filter_key("mutable_context_nodes")
    filtered["immutable_evidence_nodes"] = _filter_key("immutable_evidence_nodes")
    filtered["root_provenance_nodes"] = _filter_key("root_provenance_nodes")
    filtered["context_node_ids"] = sorted(selected_ids)
    filtered["answer_scope"] = (payload.answer_scope or "").strip()
    filtered["relevance_filter_selected_count"] = len(selected_ids)
    filtered["relevance_filter_explored_count"] = len(rows)
    return filtered


def format_retrieval_graph_context(
    finding: Dict[str, Any],
    *,
    genesis_description: Optional[str] = None,
    max_chars: int = 48000,
) -> str:
    """Serialize retrieval payload for the conversation system prompt."""
    sections: List[str] = []
    if genesis_description:
        sections.append(f"Genesis project scope:\n{genesis_description.strip()}")

    answer_scope = (finding.get("answer_scope") or "").strip()
    if answer_scope:
        sections.append(f"Answer scope (stay within this boundary):\n{answer_scope}")

    payload = {
        "mutable_hubs_relevant": finding.get("mutable_context_nodes", []),
        "immutable_evidence_relevant": finding.get("immutable_evidence_nodes", []),
        "source_documents_relevant": finding.get("root_provenance_nodes", []),
    }
    sections.append(
        "Relevance-filtered knowledge subgraph (ground answers ONLY in these concepts):\n"
        + json_dumps_ingest(payload)
    )
    text = "\n\n".join(sections)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text
