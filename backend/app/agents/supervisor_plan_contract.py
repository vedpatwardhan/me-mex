"""Structural checks for Supervisor multi-action planning (no utterance regex)."""

from __future__ import annotations

from typing import Any

from app.agents.dispatch_materializer import ordered_field_references
from app.llm.schemas import DispatchTask, WorkerRoute

_SOURCE_WORKERS = frozenset({"gist", "intradoc", "link", "reorg", "retrieval"})


def routing_binding_hints(context: dict[str, Any] | None) -> dict[str, Any]:
    fields = (context or {}).get("custom_fields") or {}
    session = (context or {}).get("session_state") or {}
    url_field_rows = [
        {"field": name, "reference": ref} for name, ref in ordered_field_references(fields)
    ]
    job_rows: list[dict[str, str]] = []
    for bucket in ("active_jobs", "recent_jobs"):
        for job in session.get(bucket) or []:
            job_id = job.get("job_id")
            if not job_id:
                continue
            job_rows.append(
                {
                    "job_id": str(job_id),
                    "worker": str(job.get("worker") or ""),
                    "status": str(job.get("status") or ""),
                    "label": str(job.get("label") or "")[:120],
                }
            )
    return {"url_field_rows": url_field_rows, "job_rows": job_rows}


def _url_count(context: dict[str, Any] | None) -> int:
    fields = (context or {}).get("custom_fields") or {}
    return len(ordered_field_references(fields))


def _active_job_count(context: dict[str, Any] | None) -> int:
    session = (context or {}).get("session_state") or {}
    return len(session.get("active_jobs") or [])


def plan_incomplete(decision: WorkerRoute, context: dict[str, Any] | None) -> bool:
    """True when Supervisor output likely failed multi-action planning (for tests/guardrails)."""
    tasks = decision.dispatch_tasks or []
    if tasks:
        return False

    if decision.fan_out_same_worker and decision.dispatch and decision.worker in _SOURCE_WORKERS:
        return False

    if decision.multi_action and not tasks and not decision.fan_out_same_worker:
        return True

    url_count = _url_count(context)
    if url_count >= 2:
        if decision.worker == "conversation" and not decision.dispatch and decision.reply:
            return True
        if (
            decision.dispatch
            and decision.worker in _SOURCE_WORKERS
            and (decision.source_field or decision.source_reference)
        ):
            return True

    return bool(
        _active_job_count(context) >= 2
        and decision.worker == "job_control"
        and decision.intent == "job_control"
        and not tasks
    )


def supervisor_max_tokens(context: dict[str, Any] | None) -> int:
    url_count = _url_count(context)
    job_count = _active_job_count(context)
    scale = max(url_count, job_count, len((context or {}).get("custom_fields") or {}))
    if scale < 2:
        return 512
    return min(2048, max(768, 160 * scale))


def structural_multi_url_dispatch_fallback(
    decision: WorkerRoute,
    context: dict[str, Any] | None,
) -> WorkerRoute:
    """When Supervisor collapsed multi-URL work into conversation, expand from binding hints only."""
    if decision.dispatch_tasks or decision.fan_out_same_worker:
        return decision
    fields = (context or {}).get("custom_fields") or {}
    rows = ordered_field_references(fields)
    if len(rows) < 2 or not plan_incomplete(decision, context):
        return decision
    tasks: list[DispatchTask] = []
    for index, (field, ref) in enumerate(rows):
        if len(rows) >= 3 and index == len(rows) - 1:
            worker, intent = "intradoc", "source_analysis"
        else:
            worker, intent = "gist", "source_summary"
        tasks.append(
            DispatchTask(
                worker=worker,
                intent=intent,
                dispatch=True,
                source_field=field,
                source_reference=ref,
            )
        )
    return decision.model_copy(
        update={
            "worker": "conversation",
            "intent": "conversation",
            "dispatch": False,
            "multi_action": True,
            "dispatch_tasks": tasks,
            "reply": None,
            "source_error": None,
            "source_field": None,
            "source_reference": None,
        }
    )


def should_append_supervisor_reply(decision: WorkerRoute, *, had_executable_tasks: bool) -> bool:
    """Narrow clarify only when tasks were dispatched and reply supplements partial plan."""
    if not had_executable_tasks or not decision.reply:
        return False
    return bool(decision.dispatch_tasks)
