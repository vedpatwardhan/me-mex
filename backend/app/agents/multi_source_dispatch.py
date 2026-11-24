"""Expand gist/intradoc dispatch when multiple sources are clearly requested."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents.source_reference import _references_in
from app.llm.schemas import WorkerRoute

_MULTI_CUE = re.compile(
    r"\b(both|all|each|every|two|three|four|multiple|several|these|those)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MultiDispatchResult:
    decisions: list[WorkerRoute]
    clarification: str | None = None


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
    if multiple_fields:
        return True
    return bool(_MULTI_CUE.search(text or ""))


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
    if decision.source_reference or decision.source_field:
        return MultiDispatchResult(decisions=[decision])

    fields = custom_fields or {}
    refs = _all_source_references(effective_text, fields)
    if len(refs) <= 1:
        return MultiDispatchResult(decisions=[decision])

    multiple_fields = _multiple_field_sources(fields)
    if not _has_multi_cue(effective_text, multiple_fields=multiple_fields):
        return MultiDispatchResult(
            decisions=[],
            clarification=(
                "I found multiple source links. Please say which one to use, "
                "or ask for both or all of them explicitly."
            ),
        )

    clones: list[WorkerRoute] = []
    for ref in refs:
        cloned = decision.model_copy(deep=True)
        cloned.source_reference = ref
        clones.append(cloned)
    return MultiDispatchResult(decisions=clones)
