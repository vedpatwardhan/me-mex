"""Mirror of backend/app/bootstrap/decision_prompt.py for Colab gateway."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if _BACKEND.is_dir():
    sys.path.insert(0, str(_BACKEND))
    from app.bootstrap.decision_prompt import (  # noqa: E402
        build_decision_prompt,
        format_assistant_relevance,
        normalize_relevance_labels,
        parse_relevance_probs,
    )
else:
    # Fallback when only colab/ was uploaded
    def build_decision_prompt(
        query: dict[str, Any], frontier: list[dict[str, Any]]
    ) -> str:
        lines = [
            "Score relevance of each frontier node to the query node.",
            'Return JSON only: {"relevance_probs": {"<frontier_id>": <0-1 float>, ...}}',
            "Probabilities must sum to 1.0 over all frontier ids.",
            "",
            f"QUERY: id={query.get('id')} kind={query.get('node_kind')} title={query.get('title')}",
        ]
        if query.get("gist"):
            lines.append(f"  gist: {str(query.get('gist'))[:400]}")
        lines.append("FRONTIER:")
        for n in frontier:
            lines.append(
                f"  - id={n.get('id')} kind={n.get('node_kind')} title={n.get('title')}"
            )
        return "\n".join(lines)

    def parse_relevance_probs(text: str, frontier_ids: set[str]) -> dict[str, float]:
        text = text.strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            text = match.group(0)
        data = json.loads(text)
        raw = data.get("relevance_probs", data)
        probs = {str(k): float(v) for k, v in raw.items() if k in frontier_ids}
        if len(probs) != len(frontier_ids):
            missing = frontier_ids - set(probs.keys())
            raise ValueError(f"missing frontier ids in model output: {missing}")
        total = sum(probs.values())
        if total <= 0:
            raise ValueError("non-positive probability sum")
        return {k: v / total for k, v in probs.items()}

    def normalize_relevance_labels(labels: dict[str, float]) -> dict[str, float]:
        if not labels:
            return {}
        total = sum(float(v) for v in labels.values())
        if total <= 0:
            n = len(labels)
            return {k: 1.0 / n for k in labels}
        return {str(k): float(v) / total for k, v in labels.items()}

    def format_assistant_relevance(labels: dict[str, float]) -> str:
        probs = normalize_relevance_labels(labels)
        return json.dumps({"relevance_probs": probs}, separators=(",", ":"))
