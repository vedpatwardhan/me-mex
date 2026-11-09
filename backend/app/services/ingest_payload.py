"""Compact JSON and ingest LLM context helpers."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.config import settings


def json_dumps_ingest(payload: Any) -> str:
    """Serialize ingestion/reorg payloads; compact when configured."""
    if settings.INGEST_JSON_COMPACT:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return json.dumps(payload, indent=2, ensure_ascii=False)


def ingest_context_message_blocks(
    query: str,
    *,
    rolling_summary: Optional[str] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
    summary_max_chars: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Build context messages for structured ingestion calls (summary + query, optional history fallback)."""
    blocks: List[Dict[str, str]] = []
    summary = (rolling_summary or "").strip()
    if settings.INGEST_USE_ROLLING_SUMMARY and summary:
        summary_cap = summary_max_chars or settings.CHAT_SUMMARY_MAX_CHARS
        blocks.append(
            {
                "role": "system",
                "content": (
                    "Conversation context (rolling summary for this project):\n"
                    f"{summary[:summary_cap]}"
                ),
            }
        )
        blocks.append({"role": "user", "content": query})
        return blocks

    if chat_history:
        tail_n = max(0, settings.INGEST_STRUCTURED_CHAT_HISTORY_TURNS)
        if tail_n:
            blocks.extend(chat_history[-tail_n:])
    if not any(m.get("content") == query for m in blocks if m.get("role") == "user"):
        blocks.append({"role": "user", "content": query})
    return blocks
