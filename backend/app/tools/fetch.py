from __future__ import annotations

import hashlib

from app.tools.search_tools import SearchTools
from app.db import ToolContext


def fetch_normalized_text(ctx: ToolContext, url: str) -> dict:
    """Return normalized text + content hash (no LLM)."""
    doc = SearchTools.fetch_document(url)
    text = doc.get("content", "") or ""
    if not text.strip() and "arxiv" in url.lower():
        hits = SearchTools.search_arxiv(url, max_results=1)
        if hits:
            text = hits[0].get("summary", "") or text
    normalized = text.strip()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return {"text": normalized, "content_hash": content_hash, "url": url}
