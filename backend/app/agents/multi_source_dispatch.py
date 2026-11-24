"""Expand gist/intradoc dispatch when multiple sources are clearly requested."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents.source_reference import _references_in
from app.llm.schemas import WorkerRoute

_MULTI_CUE = re.compile(
    r"\b(both|all|each|every|two|three|four|multiple|several|these|those|attached)\b",
    re.IGNORECASE,
)

MULTI_SOURCE_CLARIFICATION = (
    "I found multiple source links. Please say which one to use, "
    "or ask for both or all of them explicitly."
)

_GIST_CUE = re.compile(
    r"\b(summary|gist|high level|overview|concise|brief)\b",
    re.IGNORECASE,
)
_INTRADOC_CUE = re.compile(
    r"\b(detailed|deep read|intradoc|concept extraction|staging|understanding)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MultiDispatchResult:
    decisions: list[WorkerRoute]
    clarification: str | None = None


def _field_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", name)
    return (int(match.group(1)) if match else 999, name)


def ordered_field_references(fields: dict[str, Any]) -> list[tuple[str, str]]:
    """Custom-field names mapped to one canonical URL each, in stable order."""
    rows: list[tuple[str, str]] = []
    for name, value in sorted((fields or {}).items(), key=lambda item: _field_sort_key(item[0])):
        if name == "raw_text" or value is None:
            continue
        refs = sorted(_references_in(str(value)))
        if refs:
            rows.append((name, refs[0]))
    return rows


def text_requests_mixed_workers(text: str) -> bool:
    """True when the user asked for different treatments (e.g. gist + deep read) in one turn."""
    body = text or ""
    return bool(_GIST_CUE.search(body)) and bool(_INTRADOC_CUE.search(body))


def _all_source_references(text: str, fields: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    refs.update(_references_in(text or ""))
    for name, value in (fields or {}).items():
        if name == "raw_text" or value is None:
            continue
        refs.update(_references_in(str(value)))
    return sorted(refs)


def _multiple_field_sources(fields: dict[str, Any]) -> bool:
    count = 0
    for name, value in (fields or {}).items():
        if name == "raw_text" or value is None:
            continue
        if _references_in(str(value)):
            count += 1
            if count >= 2:
                return True
    return False


def _has_multi_cue(text: str, *, multiple_fields: bool) -> bool:
    body = text or ""
    if _MULTI_CUE.search(body):
        return True
    return bool(multiple_fields and re.search(r"\b(both|all|each|every)\b", body, re.IGNORECASE))


def expand_source_dispatches(
    decision: WorkerRoute,
    *,
    effective_text: str,
    custom_fields: dict[str, Any] | None,
    dispatch_allowed: bool,
) -> MultiDispatchResult:
    """Return one or more WorkerRoute clones with per-source source_reference set."""
    if not dispatch_allowed or not decision.dispatch:
        return MultiDispatchResult(decisions=[decision])
    if decision.worker not in {"gist", "intradoc"}:
        return MultiDispatchResult(decisions=[decision])
    if decision.intent not in {"source_summary", "source_analysis"}:
        return MultiDispatchResult(decisions=[decision])

    fields = custom_fields or {}
    field_refs = ordered_field_references(fields)
    multiple_fields = _multiple_field_sources(fields)
    if (
        (decision.source_reference or decision.source_field)
        and len(field_refs) > 1
        and multiple_fields
        and _has_multi_cue(effective_text, multiple_fields=multiple_fields)
        and not text_requests_mixed_workers(effective_text)
    ):
        clones: list[WorkerRoute] = []
        for field_name, ref in field_refs:
            cloned = decision.model_copy(deep=True)
            cloned.source_field = field_name
            cloned.source_reference = ref
            clones.append(cloned)
        return MultiDispatchResult(decisions=clones)
    if decision.source_reference or decision.source_field:
        return MultiDispatchResult(decisions=[decision])

    refs = _all_source_references(effective_text, fields)
    if len(refs) <= 1:
        return MultiDispatchResult(decisions=[decision])

    multiple_fields = _multiple_field_sources(fields)
    if not _has_multi_cue(effective_text, multiple_fields=multiple_fields):
        return MultiDispatchResult(
            decisions=[],
            clarification=MULTI_SOURCE_CLARIFICATION,
        )

    clones: list[WorkerRoute] = []
    for ref in refs:
        cloned = decision.model_copy(deep=True)
        cloned.source_reference = ref
        clones.append(cloned)
    return MultiDispatchResult(decisions=clones)
