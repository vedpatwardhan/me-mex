"""Emit decision-trace JSONL rows from aligned notes graph."""

from __future__ import annotations

import random
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


def emit_bootstrap_rows(
    roots: list[RootRecord],
    sections: list[SectionRecord],
    insights: list[InsightRecord],
    insight_cite_links: list[dict[str, Any]],
    *,
    seed: int = 0,
    max_frontier: int = 12,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    root_by_id = {r.root_id: r for r in roots}
    sections_l2 = [s for s in sections if s.level == 2]
    section_by_id = {s.section_id: s for s in sections}
    insight_by_id = {i.insight_id: i for i in insights}

    rows: list[dict[str, Any]] = []

    def append_row(
        query: dict,
        frontier: list[dict],
        labels: dict[str, float],
        scenario: str,
    ) -> None:
        if len(frontier) < 2:
            return
        if len(frontier) > max_frontier:
            # keep all positive-label nodes + random negatives
            must = {k for k, v in labels.items() if v > 0}
            must_nodes = [n for n in frontier if n["id"] in must]
            rest = [n for n in frontier if n["id"] not in must]
            rng.shuffle(rest)
            frontier = must_nodes + rest[: max_frontier - len(must_nodes)]
        labels = _normalize_labels(frontier, labels)
        rows.append(
            {
                "project_id": "robotics",
                "provenance": "bootstrap_notes",
                "scenario": scenario,
                "query_node": query,
                "frontier": frontier,
                "label_relevance": labels,
                "model_relevance_probs": {},
                "user_expanded_ids": [
                    k for k, v in labels.items() if v == max(labels.values())
                ],
            }
        )

    links_by_insight: dict[str, list[str]] = {}
    for link in insight_cite_links:
        links_by_insight.setdefault(link["insight_id"], []).append(link["root_id"])

    # Placement (W4): ROOT query → section hubs + insight frontier
    for link in insight_cite_links:
        root = root_by_id.get(link["root_id"])
        ins = insight_by_id.get(link["insight_id"])
        if not root or not ins:
            continue
        sec = section_by_id.get(ins.section_id)
        query = _node(root.root_id, root.title, "ROOT", root.gist)
        frontier: list[dict] = [
            _node(ins.insight_id, ins.text[:120], "CONCEPT_I"),
        ]
        labels: dict[str, float] = {ins.insight_id: 1.0}
        if sec:
            frontier.append(_node(sec.section_id, sec.title, "CONCEPT_M"))
            labels[sec.section_id] = 0.35
        for s in rng.sample(sections_l2, k=min(4, len(sections_l2))):
            if s.section_id == (sec.section_id if sec else ""):
                continue
            frontier.append(_node(s.section_id, s.title, "CONCEPT_M"))
            labels[s.section_id] = 0.0
        for other in rng.sample(insights, k=min(3, len(insights))):
            if other.insight_id == ins.insight_id:
                continue
            frontier.append(_node(other.insight_id, other.text[:80], "CONCEPT_I"))
            labels[other.insight_id] = 0.0
        append_row(query, frontier, labels, "placement")

    # Retrieval hop (W11a): section or insight query → cited ROOTs + distractors
    for ins in insights:
        root_ids = links_by_insight.get(ins.insight_id, [])
        if not root_ids:
            continue
        sec = section_by_id.get(ins.section_id)
        query_title = sec.title if sec else ins.text[:80]
        query_id = sec.section_id if sec else ins.insight_id
        query = _node(query_id, query_title, "CONCEPT_M" if sec else "CONCEPT_I")
        frontier = []
        labels = {}
        for rid in root_ids:
            r = root_by_id[rid]
            frontier.append(_node(r.root_id, r.title, "ROOT", r.gist))
            labels[r.root_id] = 1.0
        pool = [r for r in roots if r.root_id not in root_ids]
        for r in rng.sample(pool, k=min(5, len(pool))):
            frontier.append(_node(r.root_id, r.title, "ROOT"))
            labels[r.root_id] = 0.0
        append_row(query, frontier, labels, "retrieval")

    # Reorg (W5): crowded section → sibling section relocation
    by_sec: dict[str, list[InsightRecord]] = {}
    for ins in insights:
        sid = ins.section_id
        by_sec.setdefault(sid, []).append(ins)

    crowded = sorted(by_sec.items(), key=lambda x: -len(x[1]))[:8]
    for sec_id, ins_list in crowded:
        sec = section_by_id.get(sec_id)
        if not sec or len(sections_l2) < 2:
            continue
        query = _node(sec_id, sec.title, "CONCEPT_M")
        frontier = []
        labels = {sec_id: 1.0}
        frontier.append(_node(sec_id, sec.title, "CONCEPT_M"))
        siblings = [s for s in sections_l2 if s.section_id != sec_id]
        for s in rng.sample(siblings, k=min(6, len(siblings))):
            frontier.append(_node(s.section_id, s.title, "CONCEPT_M"))
            labels[s.section_id] = 0.0
        append_row(query, frontier, labels, "reorg")

    return rows
