from __future__ import annotations

import hashlib

from app.db import ToolContext
from app.services.timing import timed_tool
from app.tools.search_tools import SearchTools


@timed_tool
def fetch_normalized_text(ctx: ToolContext, url: str) -> dict:
    """Return normalized text + content hash (no LLM)."""
    doc = SearchTools.fetch_document(url)
    text = doc.get("content", "") or ""
    normalized = text.strip()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return {
        "text": normalized,
        "content_hash": content_hash,
        "url": url,
        "status": doc.get("status", "SUCCESS" if normalized else "ERROR"),
        "error": doc.get("error"),
        "doc_type": doc.get("doc_type"),
    }
