"""Foreground/background job ledger for context switch park (04 §12.5)."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from app.agents.job_affinity import JobDispatchPlan
from app.agents.jobs import new_job_id
from app.db import ToolContext

_log = logging.getLogger("memex.v2.jobs")
_registry_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_by_thread: dict[str, list[str]] = {}


def _sleep_s() -> float:
    raw = os.getenv("INTRADOC_BG_SLEEP_S", "0")
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.0


def list_jobs(thread_id: str) -> list[dict[str, Any]]:
    with _registry_lock:
        ids = list(_by_thread.get(thread_id, []))
        return [dict(_jobs[jid]) for jid in ids if jid in _jobs]


def park_active_jobs(thread_id: str) -> list[dict[str, Any]]:
    """Mark running jobs paused when user starts a new foreground turn."""
    paused: list[dict[str, Any]] = []
    with _registry_lock:
        for jid in _by_thread.get(thread_id, []):
            job = _jobs.get(jid)
            if not job or job.get("status") != "running":
                continue
            job["status"] = "paused"
            paused.append(dict(job))
    return paused


def get_job(job_id: str) -> dict[str, Any] | None:
    with _registry_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def resolve_approval_job(thread_id: str, approval_id: str, action: str) -> None:
    """Close the runtime/checkpoint job associated with a resolved approval."""
    resolved_ids: list[str] = []
    with _registry_lock:
        for jid in _by_thread.get(thread_id, []):
            job = _jobs.get(jid)
            if not job or approval_id not in {
                job.get("approval_id"),
                job.get("recommendation_id"),
            }:
                continue
            job["status"] = "done" if action == "approve" else "dismissed"
            job["approval_resolution"] = action
            job["progress"] = "approved" if action == "approve" else "dismissed"
            resolved_ids.append(jid)

    from app.agents.session_plane import resolve_job_records

    resolve_job_records(thread_id, resolved_ids, action, approval_id=approval_id)


def reconcile_pending_approvals(thread_id: str, pending_approval_ids: set[str]) -> None:
    """Drop stale awaiting-approval status when the approval is no longer pending."""
    resolved_ids: list[str] = []
    with _registry_lock:
        for jid in _by_thread.get(thread_id, []):
            job = _jobs.get(jid)
            if not job or job.get("status") != "awaiting_approval":
                continue
            approval_id = job.get("approval_id") or job.get("recommendation_id")
            if approval_id and approval_id not in pending_approval_ids:
                job["status"] = "resolved"
                job["progress"] = "approval resolved"
                resolved_ids.append(jid)

    if resolved_ids:
        from app.agents.session_plane import resolve_job_records

        resolve_job_records(thread_id, resolved_ids, "resolved")


def resume_job(job_id: str) -> dict[str, Any] | None:
    with _registry_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job["status"] = "running"
        return dict(job)


def _finish_job(job_id: str, output: dict[str, Any], *, project_id: str | None = None) -> None:
    job_snapshot: dict[str, Any] | None = None
    with _registry_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "awaiting_approval" if output.get("approval_id") else "done"
        job["output"] = output
        job["progress"] = output.get("reply", "")
        if output.get("approval_id"):
            job["recommendation_id"] = output.get("approval_id")
            job["approval_id"] = output.get("approval_id")
        job_snapshot = dict(job)
        pid = project_id or job.get("project_id")
        tid = job.get("thread_id")

    if job_snapshot:
        _log.info(
            "job_status job_id=%s worker=%s status=%s thread_id=%s project_id=%s",
            job_snapshot.get("job_id"),
            job_snapshot.get("worker"),
            job_snapshot.get("status"),
            job_snapshot.get("thread_id"),
            pid or job_snapshot.get("project_id"),
        )

    if job_snapshot and pid and tid:
        from app.agents.session_plane import observer_ingest_job

        observer_ingest_job(
            project_id=pid,
            thread_id=tid,
            job=job_snapshot,
            worker_output=output,
        )


def dispatch_background_worker(
    *,
    thread_id: str,
    worker_kind: str,
    ctx: ToolContext,
    text: str,
    context: dict,
    worker_fn: Callable[[ToolContext, str, dict], dict],
    project_id: str | None = None,
    plan: JobDispatchPlan | None = None,
) -> dict[str, Any] | None:
    if plan is not None and plan.action == "skip":
        return None

    pid = project_id or ctx.project_id
    affinity_key = (plan.affinity_key if plan else "") or f"{worker_kind}:{pid}"
    dispatch_ctx = dict(context)
    if plan and plan.approval_id:
        dispatch_ctx["approval_id"] = plan.approval_id
    if plan and plan.action == "update":
        dispatch_ctx["job_update"] = True

    job_id: str
    if plan and plan.action == "update" and plan.job_id:
        job_id = plan.job_id
        with _registry_lock:
            job = _jobs.get(job_id)
            if job:
                job["status"] = "running"
                job["label"] = (text or worker_kind)[:80]
                job["request_text"] = (text or "")[:4000]
                job["affinity_key"] = affinity_key
                if plan.approval_id:
                    job["approval_id"] = plan.approval_id
                record = dict(job)
            else:
                job_id = new_job_id()
                record = _new_job_record(job_id, worker_kind, thread_id, pid, text, affinity_key)
                _jobs[job_id] = record
                _by_thread.setdefault(thread_id, []).append(job_id)
    else:
        job_id = new_job_id()
        record = _new_job_record(job_id, worker_kind, thread_id, pid, text, affinity_key)
        with _registry_lock:
            _jobs[job_id] = record
            _by_thread.setdefault(thread_id, []).append(job_id)

    def _run() -> None:
        sleep_s = _sleep_s()
        if sleep_s and worker_kind == "intradoc":
            time.sleep(sleep_s)
        with _registry_lock:
            st = _jobs.get(job_id, {}).get("status")
        if st == "cancelled":
            return
        try:
            out = worker_fn(ctx, text, dispatch_ctx)
            _finish_job(job_id, out, project_id=pid)
        except Exception as exc:  # noqa: BLE001
            _finish_job(
                job_id,
                {"reply": str(exc), "graph_write": False, "error": True},
                project_id=pid,
            )

    _log.info(
        "job_start job_id=%s worker=%s thread_id=%s project_id=%s",
        job_id,
        worker_kind,
        thread_id,
        pid,
    )
    threading.Thread(target=_run, daemon=True).start()
    return dict(record)


def _new_job_record(
    job_id: str,
    worker_kind: str,
    thread_id: str,
    project_id: str,
    text: str,
    affinity_key: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "kind": worker_kind,
        "label": (text or worker_kind)[:80],
        "request_text": (text or "")[:4000],
        "status": "running",
        "worker": worker_kind,
        "thread_id": thread_id,
        "project_id": project_id,
        "progress": "running",
        "affinity_key": affinity_key,
    }


def start_background_worker(
    *,
    thread_id: str,
    worker_kind: str,
    ctx: ToolContext,
    text: str,
    context: dict,
    worker_fn: Callable[[ToolContext, str, dict], dict],
    project_id: str | None = None,
) -> dict[str, Any]:
    plan = JobDispatchPlan(
        action="create", affinity_key=f"{worker_kind}:{project_id or ctx.project_id}"
    )
    result = dispatch_background_worker(
        thread_id=thread_id,
        worker_kind=worker_kind,
        ctx=ctx,
        text=text,
        context=context,
        worker_fn=worker_fn,
        project_id=project_id,
        plan=plan,
    )
    assert result is not None
    return result


def start_background_intradoc(
    *,
    thread_id: str,
    ctx: ToolContext,
    text: str,
    context: dict,
    worker_fn: Callable[[ToolContext, str, dict], dict],
) -> dict[str, Any]:
    return start_background_worker(
        thread_id=thread_id,
        worker_kind="intradoc",
        ctx=ctx,
        text=text,
        context=context,
        worker_fn=worker_fn,
        project_id=ctx.project_id,
    )
