"""Append live decision-trace rows for eval / optional reranker refresh ([05 §8])."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger("memex.v2.decision_trace")

_lock = __import__("threading").Lock()


def _trace_dir() -> Path:
    return Path(settings.DECISION_TRACE_DIR)


def append_decision_trace_row(project_id: str, row: dict[str, Any]) -> Path | None:
    """Append one JSON object per line. Returns path written or None if disabled."""
    if not settings.DECISION_TRACE_ENABLED:
        return None
    if not project_id:
        project_id = "unknown"
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = _trace_dir() / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day}.jsonl"
    line = {**row}
    line.setdefault("timestamp", datetime.now(UTC).isoformat())
    line.setdefault("project_id", project_id)
    line.setdefault("provenance", "live_session")
    payload = json.dumps(line, ensure_ascii=False) + "\n"
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(payload)
    logger.debug("appended decision trace %s scenario=%s", path.name, row.get("scenario"))
    return path


def frontier_from_scorer_nodes(nodes: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in nodes:
        if hasattr(n, "__dict__"):
            d = dict(n.__dict__)
        elif isinstance(n, dict):
            d = dict(n)
        else:
            continue
        out.append(
            {
                "id": d.get("id", ""),
                "title": d.get("title", ""),
                "node_kind": d.get("node_kind", ""),
            }
        )
    return out


def query_node_dict(node: Any) -> dict[str, Any]:
    if hasattr(node, "__dict__"):
        d = dict(node.__dict__)
    elif isinstance(node, dict):
        d = dict(node)
    else:
        return {"id": "", "title": "", "node_kind": ""}
    return {
        "id": d.get("id", ""),
        "title": d.get("title", ""),
        "node_kind": d.get("node_kind", ""),
    }
