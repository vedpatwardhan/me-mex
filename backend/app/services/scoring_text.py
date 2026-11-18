"""Format graph nodes as cross-encoder query / candidate text."""

from __future__ import annotations

from typing import Any

from app.models import Node

MAX_BODY_CHARS = 512


def format_scorer_document(node: dict[str, Any]) -> str:
    """Single text block for query or frontier candidate in a reranker pair."""
    kind = str(node.get("node_kind") or "").strip()
    title = str(node.get("title") or node.get("id") or "").strip()
    body = str(
        node.get("gist") or node.get("description") or node.get("body") or ""
    ).strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[: MAX_BODY_CHARS - 1] + "…"
    lines = [f"[{kind}] {title}" if kind else title]
    if body:
        lines.append(body)
    return "\n".join(lines)


def scorer_node_to_dict(
    *,
    id: str,
    title: str,
    node_kind: str,
    gist: str = "",
    description: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "title": title,
        "node_kind": node_kind,
        "gist": gist,
        "description": description,
    }


def node_model_to_scorer_dict(node: Node) -> dict[str, Any]:
    return scorer_node_to_dict(
        id=node.id,
        title=node.title,
        node_kind=node.node_kind.value,
        description=node.description or "",
    )


def logits_to_relevance_probs(
    ids: list[str], logits: list[float]
) -> dict[str, float]:
    """Softmax over frontier ids (mirrors gateway)."""
    if not ids:
        return {}
    if len(ids) != len(logits):
        raise ValueError("ids and logits length mismatch")
    import math

    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps)
    if total <= 0:
        u = 1.0 / len(ids)
        return dict.fromkeys(ids, u)
    return {nid: e / total for nid, e in zip(ids, exps, strict=True)}