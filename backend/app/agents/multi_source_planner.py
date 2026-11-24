"""Deterministic multi-paper task planning (gist vs intradoc per field)."""

from __future__ import annotations

import re
from typing import Any

from app.agents.multi_source_dispatch import (
    MULTI_SOURCE_CLARIFICATION,
    MultiDispatchResult,
    _has_multi_cue,
    _multiple_field_sources,
    ordered_field_references,
    text_requests_mixed_workers,
)
from app.llm.schemas import WorkerRoute

_GIST_CUE = re.compile(
    r"\b(summary|gist|high level|overview|concise|brief)\b",
    re.IGNORECASE,
)
_INTRADOC_CUE = re.compile(
    r"\b(detailed|deep read|intradoc|concept extraction|staging|understanding)\b",
    re.IGNORECASE,
)
_FIRST_TWO = re.compile(r"\bfirst\s+two\b", re.IGNORECASE)
_THIRD = re.compile(r"\bthird\b", re.IGNORECASE)


def _utterance_before_field_append(effective_text: str, fields: dict[str, Any]) -> str:
    """Custom fields are appended as key=value lines; heuristics must ignore that suffix."""
    body = effective_text or ""
    cut = len(body)
    for name in fields:
        if name == "raw_text":
            continue
        marker = f"{name}="
        index = body.find(marker)
        if index >= 0:
            cut = min(cut, index)
    return body[:cut].strip() if cut < len(body) else body


def _assignment_vector(
    text: str,
    field_refs: list[tuple[str, str]],
) -> list[tuple[str, str] | None]:
    """Map field index -> (worker, intent) when phrasing is explicit."""
    field_count = len(field_refs)
    if field_count < 2:
        return []
    text_l = text.lower()
    assign: list[tuple[str, str] | None] = [None] * field_count
    gist = ("gist", "source_summary")
    intradoc = ("intradoc", "source_analysis")

    if _FIRST_TWO.search(text) and field_count >= 2 and _GIST_CUE.search(text):
        assign[0] = gist
        assign[1] = gist

    if _THIRD.search(text) and field_count >= 3 and _INTRADOC_CUE.search(text):
        assign[2] = intradoc

    for index, (field_name, _ref) in enumerate(field_refs):
        name = field_name.lower()
        if name not in text_l:
            continue
        window = text_l
        pos = text_l.find(name)
        if pos >= 0:
            window = text_l[max(0, pos - 40) : pos + len(name) + 60]
        if _INTRADOC_CUE.search(window):
            assign[index] = intradoc
        elif _GIST_CUE.search(window) and assign[index] is None:
            assign[index] = gist

    return assign


def plan_multi_source_tasks(
    decision: WorkerRoute,
    *,
    effective_text: str,
    custom_fields: dict[str, Any] | None,
    dispatch_allowed: bool,
) -> MultiDispatchResult | None:
    """Return multi-route plan when per-paper worker assignment is clear; else None."""
    if not dispatch_allowed or not decision.dispatch:
        return None
    if decision.worker not in {"gist", "intradoc", "conversation"}:
        return None

    fields = custom_fields or {}
    field_refs = ordered_field_references(fields)
    if len(field_refs) < 2:
        return None

    multiple_fields = _multiple_field_sources(fields)
    if not _has_multi_cue(effective_text, multiple_fields=multiple_fields):
        return None

    if not text_requests_mixed_workers(effective_text):
        return None

    utterance = _utterance_before_field_append(effective_text, fields)
    assignments = _assignment_vector(utterance, field_refs)
    if not assignments or any(slot is None for slot in assignments):
        return MultiDispatchResult(decisions=[], clarification=MULTI_SOURCE_CLARIFICATION)

    decisions: list[WorkerRoute] = []
    for (field_name, ref), slot in zip(field_refs, assignments, strict=True):
        worker, intent = slot
        decisions.append(
            WorkerRoute(
                worker=worker,
                intent=intent,
                dispatch=True,
                reply=None,
                source_field=field_name,
                source_reference=ref,
            )
        )
    return MultiDispatchResult(decisions=decisions)
