"""Assemble retrieved subgraph context (mutable traversal + immutable evidence closure)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from app.db import db_engine
from app.models import GraphNode
from app.services.graph_analytics import MutableTreeIndex
from app.services.ingest_payload import json_dumps_ingest


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

    payload = {
        "mutable_hubs_traversed": finding.get("mutable_context_nodes", []),
        "immutable_evidence_linked_to_traversed_hubs": finding.get(
            "immutable_evidence_nodes", []
        ),
        "source_documents": finding.get("root_provenance_nodes", []),
        "traversed_mutable_node_ids": [
            r["id"] for r in finding.get("mutable_context_nodes", []) if r.get("id")
        ],
    }
    sections.append(
        "Retrieved knowledge subgraph (ground answers in these concepts only):\n"
        + json_dumps_ingest(payload)
    )
    text = "\n\n".join(sections)
    if len(text) > max_chars:
        return text[: max_chars - 3] + "..."
    return text
