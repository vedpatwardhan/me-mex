"""Mechanical expansion of Supervisor dispatch_tasks (no utterance pattern matching)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents.source_reference import _references_in, resolve_source_reference
from app.llm.schemas import DispatchTask, WorkerRoute

_MULTI_SOURCE_CLARIFICATION = (
    "I need a clear plan per source or job. Use dispatch_tasks in the supervisor "
    "or say which link or dock job each action applies to."
)


@dataclass(frozen=True)
class MultiDispatchResult:
    decisions: list[WorkerRoute]
    clarification: str | None = None


def _field_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", name)
    return (int(match.group(1)) if match else 999, name)


def ordered_field_references(fields: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for name, value in sorted((fields or {}).items(), key=lambda item: _field_sort_key(item[0])):
        if name == "raw_text" or value is None:
            continue
        refs = sorted(_references_in(str(value)))
        if refs:
            rows.append((name, refs[0]))
    return rows


def _known_job_ids(session_jobs: dict[str, Any] | None) -> set[str]:
    ids: set[str] = set()
    for bucket in ("active_jobs", "recent_jobs"):
        for job in (session_jobs or {}).get(bucket) or []:
            job_id = job.get("job_id")
            if job_id:
                ids.add(str(job_id))
    return ids


def _task_to_route(task: DispatchTask) -> WorkerRoute:
    return WorkerRoute(
        worker=task.worker,
        intent=task.intent,
        dispatch=task.dispatch,
        reply=task.reply,
        source_field=task.source_field,
        source_reference=task.source_reference,
        source_error=task.source_error,
        title=task.title,
        content=task.content,
        target_id=task.target_id,
        job_action=task.job_action,
        root_id=task.root_id,
        target_ids=task.target_ids,
    )


def _validate_task(
    route: WorkerRoute,
    *,
    effective_text: str,
    custom_fields: dict[str, Any],
    session_jobs: dict[str, Any] | None,
) -> str | None:
    if route.worker == "job_control" or route.intent == "job_control":
        if route.job_action not in {"pause", "resume", "cancel", "delete"}:
            return "Each job control action needs a job_action (pause, resume, cancel, delete)."
        job_id = str(route.target_id or "")
        if not job_id or job_id not in _known_job_ids(session_jobs):
            return "That job_id is not in the dock queue for this thread."
        return None

    if route.intent in {"source_summary", "source_analysis"}:
        source = resolve_source_reference(
            effective_text,
            custom_fields,
            selected_reference=route.source_reference,
            selected_field=route.source_field,
        )
        if source.error:
            return source.error
        if not source.url and not str((custom_fields or {}).get("raw_text") or "").strip():
            return "The selected source field doesn't contain a readable link or arXiv ID."
        return None

    if route.intent == "status" and route.target_id:
        job_id = str(route.target_id)
        if job_id not in _known_job_ids(session_jobs):
            return "I couldn't find that job in the dock queue for this thread."
    return None


def _apply_source_resolution(
    route: WorkerRoute,
    *,
    effective_text: str,
    custom_fields: dict[str, Any],
) -> WorkerRoute:
    if route.intent not in {"source_summary", "source_analysis"}:
        return route
    source = resolve_source_reference(
        effective_text,
        custom_fields,
        selected_reference=route.source_reference,
        selected_field=route.source_field,
    )
    if source.url:
        updates: dict[str, Any] = {"source_reference": source.url}
        if source.field_name:
            updates["source_field"] = source.field_name
        return route.model_copy(update=updates)
    return route


def _multi_source_gate_violation(decision: WorkerRoute, fields: dict[str, Any]) -> bool:
    url_fields = ordered_field_references(fields)
    if len(url_fields) < 2:
        return False
    if decision.dispatch_tasks or decision.fan_out_same_worker:
        return False
    if not decision.multi_action:
        return False
    if not decision.dispatch:
        return False
    if decision.worker not in {"gist", "intradoc", "link", "reorg", "retrieval"}:
        return False
    return bool(decision.source_field or decision.source_reference)


def materialize_dispatches(
    decision: WorkerRoute,
    *,
    effective_text: str,
    custom_fields: dict[str, Any] | None,
    session_jobs: dict[str, Any] | None,
    dispatch_allowed: bool,
) -> MultiDispatchResult:
    """Validate Supervisor output and emit one WorkerRoute per action."""
    fields = custom_fields or {}

    if decision.dispatch_tasks:
        routes: list[WorkerRoute] = []
        for task in decision.dispatch_tasks:
            route = _task_to_route(task)
            error = _validate_task(
                route,
                effective_text=effective_text,
                custom_fields=fields,
                session_jobs=session_jobs,
            )
            if error:
                return MultiDispatchResult(decisions=[], clarification=error)
            route = _apply_source_resolution(
                route,
                effective_text=effective_text,
                custom_fields=fields,
            )
            routes.append(route)
        if not routes:
            return MultiDispatchResult(
                decisions=[],
                clarification="No actions were listed in dispatch_tasks.",
            )
        return MultiDispatchResult(decisions=routes)

    if decision.fan_out_same_worker and dispatch_allowed and decision.dispatch:
        if decision.worker not in {"gist", "intradoc"}:
            return MultiDispatchResult(decisions=[decision])
        if decision.intent not in {"source_summary", "source_analysis"}:
            return MultiDispatchResult(decisions=[decision])
        field_refs = ordered_field_references(fields)
        if len(field_refs) <= 1:
            return MultiDispatchResult(decisions=[decision])
        clones: list[WorkerRoute] = []
        for field_name, ref in field_refs:
            cloned = decision.model_copy(deep=True)
            cloned.source_field = field_name
            cloned.source_reference = ref
            clones.append(cloned)
        return MultiDispatchResult(decisions=clones)

    if _multi_source_gate_violation(decision, fields):
        return MultiDispatchResult(decisions=[], clarification=_MULTI_SOURCE_CLARIFICATION)

    if decision.source_error:
        return MultiDispatchResult(
            decisions=[],
            clarification=str(decision.source_error),
        )

    single = _apply_source_resolution(
        decision,
        effective_text=effective_text,
        custom_fields=fields,
    )
    return MultiDispatchResult(decisions=[single])
