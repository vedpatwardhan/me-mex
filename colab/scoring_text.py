"""Mirror of backend/app/services/scoring_text.py for Colab gateway."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))
    from app.services.scoring_text import (  # noqa: E402
        format_scorer_document,
        logits_to_relevance_probs,
        scorer_node_to_dict,
    )
else:

    MAX_BODY_CHARS = 512

    def format_scorer_document(node: dict[str, Any]) -> str:
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

    def logits_to_relevance_probs(
        ids: list[str], logits: list[float]
    ) -> dict[str, float]:
        import math

        if not ids:
            return {}
        m = max(logits)
        exps = [math.exp(x - m) for x in logits]
        total = sum(exps)
        if total <= 0:
            u = 1.0 / len(ids)
            return dict.fromkeys(ids, u)
        return {nid: e / total for nid, e in zip(ids, exps, strict=True)}