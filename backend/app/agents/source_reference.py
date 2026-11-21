"""Resolve user-provided document references from text and custom-field values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_ARXIV_ID = re.compile(r"(?<![\w.])(\d{4}\.\d{4,5}(?:v\d+)?)(?![\w.])", re.IGNORECASE)
_TRAILING_URL_PUNCTUATION = ".,;:!?)]}>\"'`"


@dataclass(frozen=True)
class SourceReference:
    url: str | None = None
    error: str | None = None


def resolve_source_reference(
    text: str,
    custom_fields: dict[str, Any] | None = None,
) -> SourceReference:
    """Find a single supplied URL or arXiv identifier without relying on field names."""
    values = [text or ""]
    values.extend(str(value) for value in (custom_fields or {}).values() if value is not None)

    urls: set[str] = set()
    arxiv_ids: set[str] = set()
    for value in values:
        for match in _URL.findall(value):
            candidate = match.rstrip(_TRAILING_URL_PUNCTUATION)
            parts = urlsplit(candidate)
            if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
                continue
            if "arxiv.org" in parts.netloc.lower():
                parts = _arxiv_pdf_url(parts)
                candidate = urlunsplit(parts)
            urls.add(candidate)
        arxiv_ids.update(match.group(1) for match in _ARXIV_ID.finditer(value))

    if len(urls) > 1:
        return SourceReference(
            error="I found multiple source links. Please specify which one to use."
        )
    if urls:
        return SourceReference(url=next(iter(urls)))
    if len(arxiv_ids) > 1:
        return SourceReference(
            error="I found multiple arXiv IDs. Please specify which paper to use."
        )
    if arxiv_ids:
        arxiv_id = next(iter(arxiv_ids))
        return SourceReference(url=f"https://arxiv.org/pdf/{arxiv_id}")
    return SourceReference()


def source_request_worker(text: str, context: dict[str, Any]) -> str | None:
    """Route short source summaries to gist and detailed source work to intradoc."""
    fields = context.get("custom_fields") or {}
    source = resolve_source_reference(text, fields)
    if not source.url and not source.error and not str(fields.get("raw_text") or "").strip():
        return None

    lower = text.lower()
    detailed = re.search(
        r"\b(deep[ -]?read|deep dive|intra[ -]?doc|detailed|in[- ]depth|in detail|"
        r"comprehensive|thorough|analysis|analy[sz]e|walk (?:me )?through|"
        r"extract (?:the )?concepts?|concept graph)\b",
        lower,
    )
    if detailed:
        return "intradoc"

    short_summary = re.search(
        r"\b(gist|summary|summaries|summari[sz](?:e|es|ed|ing|ation)|recap|"
        r"(?:quick|short|brief) summary|brief overview|quick overview|executive summary|"
        r"in a few sentences|overview|main idea|key takeaways?|what.{0,30}about|"
        r"tell me (?:briefly )?about|explain (?:the )?(?:paper|article|source))\b",
        lower,
    )
    return "gist" if short_summary else None


def _arxiv_pdf_url(parts):
    host = parts.netloc.lower()
    if host not in {"arxiv.org", "www.arxiv.org"}:
        return parts
    path = re.sub(r"^/(?:abs|html)/", "/pdf/", parts.path)
    return parts._replace(path=path)
