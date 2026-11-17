"""Emit decision-trace JSONL from notes alignment.

Primary training shape (placement / class):
  - query = paper (ROOT + gist from deeper_read)
  - frontier = flat insight subsections (category labels in overall_insights)
  - label = 1.0 on subsection(s) where that paper appears in parentheses
"""

from __future__ import annotations

from typing import Any

from app.bootstrap.alignment import InsightRecord, RootRecord, SectionRecord


def _node(node_id: str, title: str, kind: str, gist: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": node_id,
        "title": title,
        "node_kind": kind,
    }
    if gist:
        out["gist"] = gist[:500]
    return out


def _normalize_labels(
    frontier: list[dict], labels: dict[str, float]
) -> dict[str, float]:
    ids = {n["id"] for n in frontier}
    filt = {k: float(v) for k, v in labels.items() if k in ids}
    for nid in ids:
        filt.setdefault(nid, 0.0)
    total = sum(filt.values())
    if total <= 0:
        u = 1.0 / len(ids)
        return {k: u for k in ids}
    return {k: v / total for k, v in filt.items()}


def _category_nodes(
    sections: list[SectionRecord], insights: list[InsightRecord]
) -> list[dict[str, Any]]:
    """Flat subsection classes that actually contain numbered notes."""
    used = {ins.section_id for ins in insights}
    categories: list[dict[str, Any]] = []
    for sec in sections:
        if sec.section_id not in used:
            continue
        display = sec.flat_title or sec.title
        categories.append(_node(sec.section_id, display, "CONCEPT_M"))
    return categories


def emit_bootstrap_rows(
    roots: list[RootRecord],
    sections: list[SectionRecord],
    insights: list[InsightRecord],
    insight_cite_links: list[dict[str, Any]],
    *,
    seed: int = 0,
    max_frontier: int | None = None,
) -> list[dict[str, Any]]:
    _ = seed  # reserved for future negative sampling
    root_by_id = {r.root_id: r for r in roots}
    categories = _category_nodes(sections, insights)
    if len(categories) < 2:
        return []

    cat_ids = {c["id"] for c in categories}
    root_to_categories: dict[str, set[str]] = {}
    for link in insight_cite_links:
        ins = next((i for i in insights if i.insight_id == link["insight_id"]), None)
        if not ins or ins.section_id not in cat_ids:
            continue
        root_to_categories.setdefault(link["root_id"], set()).add(ins.section_id)

    rows: list[dict[str, Any]] = []
    frontier = categories if max_frontier is None else categories

    for root_id, positive_cat_ids in sorted(root_to_categories.items()):
        root = root_by_id.get(root_id)
        if not root:
            continue
        query = _node(root.root_id, root.title, "ROOT", root.gist)
        labels = {cid: (1.0 if cid in positive_cat_ids else 0.0) for cid in cat_ids}
        labels = _normalize_labels(frontier, labels)
        rows.append(
            {
                "project_id": "robotics",
                "provenance": "bootstrap_notes",
                "scenario": "placement_subsection",
                "query_node": query,
                "frontier": frontier,
                "label_relevance": labels,
                "model_relevance_probs": {},
                "user_expanded_ids": sorted(positive_cat_ids),
            }
        )

    return rows
