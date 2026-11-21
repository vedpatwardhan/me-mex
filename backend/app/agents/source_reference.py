"""Validate Supervisor-selected source references against user-supplied input."""

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
    field_name: str | None = None


def resolve_source_reference(
    text: str,
    custom_fields: dict[str, Any] | None = None,
    *,
    selected_reference: str | None = None,
    selected_field: str | None = None,
) -> SourceReference:
    """Validate the Supervisor's selection; recognize URL syntax only for checking it."""
    fields = custom_fields or {}
    if selected_field is not None and selected_field not in fields:
        return SourceReference(error="The selected source field is not present in the request.")

    supplied: dict[str, set[str]] = {"$utterance": _references_in(text or "")}
    for name, value in fields.items():
        if name == "raw_text" or value is None:
            continue
        supplied[str(name)] = _references_in(str(value))

    field_candidates = supplied.get(selected_field, set()) if selected_field else set()
    if selected_reference:
        selected_candidates = _references_in(selected_reference)
        if len(selected_candidates) != 1:
            return SourceReference(
                error="The selected source reference is not a single URL or arXiv ID."
            )
        selected = next(iter(selected_candidates))
        allowed = field_candidates if selected_field else set().union(*supplied.values())
        if selected not in allowed:
            return SourceReference(
                error="The selected source reference does not match a link or arXiv ID the user supplied."
            )
        field_name = selected_field or _unique_field_for(selected, supplied)
        return SourceReference(url=selected, field_name=field_name)

    candidates = field_candidates if selected_field else set().union(*supplied.values())
    if not candidates:
        return SourceReference(field_name=selected_field)
    if len(candidates) > 1:
        return SourceReference(
            error="I found multiple possible source references. Please specify which one to use."
        )
    selected = next(iter(candidates))
    field_name = selected_field or _unique_field_for(selected, supplied)
    return SourceReference(url=selected, field_name=field_name)


def _unique_field_for(reference: str, supplied: dict[str, set[str]]) -> str | None:
    fields = [
        name
        for name, candidates in supplied.items()
        if name != "$utterance" and reference in candidates
    ]
    return fields[0] if len(fields) == 1 else None


def _references_in(value: str) -> set[str]:
    """Extract candidate URL syntax for validation, not semantic source selection."""
    urls: set[str] = set()
    arxiv_ids: set[str] = set()
    for match in _URL.findall(value):
        candidate = match.rstrip(_TRAILING_URL_PUNCTUATION)
        parts = urlsplit(candidate)
        if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
            continue
        if "arxiv.org" in parts.netloc.lower():
            parts = _arxiv_pdf_url(parts)
            candidate = urlunsplit(parts)
        urls.add(candidate)
    if urls:
        return urls
    arxiv_ids.update(match.group(1) for match in _ARXIV_ID.finditer(value))
    return {f"https://arxiv.org/pdf/{arxiv_id}" for arxiv_id in arxiv_ids}


def _arxiv_pdf_url(parts):
    host = parts.netloc.lower()
    if host not in {"arxiv.org", "www.arxiv.org"}:
        return parts
    path = re.sub(r"^/(?:abs|html)/", "/pdf/", parts.path)
    return parts._replace(path=path)
