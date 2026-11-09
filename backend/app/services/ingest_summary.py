"""User-facing ingestion completion messages (no pipeline event dump)."""

from __future__ import annotations

import json
from typing import Any, Dict, List


def query_asks_system_status(query: str) -> bool:
    """True when the user explicitly asks about jobs, progress, or system activity."""
    q = (query or "").lower()
    markers = (
        "status",
        "progress",
        "ingestion",
        "background job",
        "what happened",
        "still running",
        "system event",
        "how long",
    )
    return any(m in q for m in markers)


def build_ingestion_summary_user_message(
    doc_title: str,
    doc_description: str,
    canonical_concepts: List[Dict[str, Any]],
) -> str:
    """Structured user turn for post-ingestion chat (titles + blurbs only)."""
    concepts_json = json.dumps(canonical_concepts, ensure_ascii=False, indent=2)
    gist = (doc_description or "").strip() or "(no summary)"
    return (
        "The document below was ingested successfully. Write the user notification "
        "using the required format in your system instructions.\n\n"
        f"Document title: {doc_title}\n\n"
        f"Document gist: {gist}\n\n"
        f"Main canonical concepts (JSON):\n{concepts_json}"
    )
