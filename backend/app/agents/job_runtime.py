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
_cancel_events: dict[str, threading.Event] = {}
_resume_events: dict[str, threading.Event] = {}


class JobCancelled(Exception):
    """Raised at a cooperative checkpoint after a user cancels a background job."""


def checkpoint_job(context: dict[str, Any]) -> None:
    """Pause at worker-safe boundaries and raise if the job has been cancelled."""
    control = context.get("_job_control") or {}
    cancelled = control.get("cancel_event")
    resume = control.get("resume_event")
    if cancelled is None or resume is None:
        return
    while not resume.wait(timeout=0.1):
        if cancelled.is_set():
            raise JobCancelled
    if cancelled.is_set():
        raise JobCancelled


def _publish_job_update(job: dict[str, Any], source: str = "control") -> None:
    from app.agents.session_events import publish_session_event

    publish_session_event(
        str(job.get("thread_id") or ""),
        {"type": "job_update", "job": job, "source": source},
    )


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
            _resume_events.setdefault(jid, threading.Event()).clear()
            paused.append(dict(job))
    if paused:
        from app.agents.session_plane import update_job_record_status

    for job in paused:
        update_job_record_status(
            thread_id,
            str(job["job_id"]),
            str(job["status"]),
            str(job.get("progress") or "paused"),
        )
        _publish_job_update(job, source="context_switch")
    return paused


def get_job(job_id: str) -> dict[str, Any] | None:
    with _registry_lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def control_job(
    thread_id: str,
    job_id: str,
    action: str,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Pause, resume, cancel, or remove one job belonging to a thread."""
    if action not in {"pause", "resume", "cancel", "delete"}:
        raise ValueError(f"Unsupported job action: {action}")

    approval_id: str | None = None
    with _registry_lock:
        job = _jobs.get(job_id)
        if (
            not job
            or job.get("thread_id") != thread_id
            or (project_id is not None and job.get("project_id") != project_id)
        ):
            raise ValueError("Job not found in this thread")
        status = job.get("status")
        if action == "pause":
            if status != "running":
                raise ValueError("Only running jobs can be paused")
            job["status"] = "paused"
            job["progress"] = "paused by user"
            _resume_events.setdefault(job_id, threading.Event()).clear()
        elif action == "resume":
            if status != "paused":
                raise ValueError("Only paused jobs can be resumed")
            job["status"] = "running"
            job["progress"] = "resumed by user"
            _resume_events.setdefault(job_id, threading.Event()).set()
        elif action == "cancel":
            if status not in {"running", "paused", "awaiting_approval"}:
                raise ValueError("Only open jobs can be cancelled")
            job["status"] = "cancelled"
            job["progress"] = "cancelled by user"
            _cancel_events.setdefault(job_id, threading.Event()).set()
            _resume_events.setdefault(job_id, threading.Event()).set()
            approval_id = job.get("approval_id") or job.get("recommendation_id")
        else:
            if status in {"running", "paused", "awaiting_approval"}:
                raise ValueError("Cancel or finish an open job before deleting it")
            job["status"] = "deleted"
            job["progress"] = "removed from queue"
        snapshot = dict(job)

    if approval_id and action == "cancel":
        try:
            from app.db import get_store

            get_store().resolve_approval(approval_id, "dismiss")
        except Exception:  # noqa: BLE001 - cancelling the worker remains effective
            _log.exception("Failed to dismiss approval for cancelled job %s", job_id)

    from app.agents.session_plane import remove_job_record, update_job_record_status

    if action == "delete":
        with _registry_lock:
            _jobs.pop(job_id, None)
            ids = _by_thread.get(thread_id, [])
            _by_thread[thread_id] = [jid for jid in ids if jid != job_id]
            _cancel_events.pop(job_id, None)
            _resume_events.pop(job_id, None)
        remove_job_record(thread_id, job_id)
        from app.agents.session_events import publish_session_event

        publish_session_event(thread_id, {"type": "job_delete", "job_id": job_id})
        return snapshot

    update_job_record_status(thread_id, job_id, snapshot["status"], snapshot["progress"])
    if approval_id and action == "cancel":
        from app.agents.session_plane import resolve_job_records

        resolve_job_records(thread_id, [job_id], "cancel", approval_id=approval_id)
    _publish_job_update(snapshot)
    return snapshot


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
        job["progress"] = "resumed"
        _resume_events.setdefault(job_id, threading.Event()).set()
        return dict(job)


def _finish_job(job_id: str, output: dict[str, Any], *, project_id: str | None = None) -> None:
    job_snapshot: dict[str, Any] | None = None
    with _registry_lock:
        job = _jobs.get(job_id)
        if not job or job.get("status") in {"cancelled", "deleted"}:
            return
        job["status"] = (
            "error"
            if output.get("error")
            else "awaiting_approval"
            if output.get("approval_id")
            else "done"
        )
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
                _cancel_events.setdefault(job_id, threading.Event()).clear()
                _resume_events.setdefault(job_id, threading.Event()).set()
            else:
                job_id = new_job_id()
                record = _new_job_record(job_id, worker_kind, thread_id, pid, text, affinity_key)
                _jobs[job_id] = record
                _by_thread.setdefault(thread_id, []).append(job_id)
                _cancel_events[job_id] = threading.Event()
                _resume_events[job_id] = threading.Event()
                _resume_events[job_id].set()
    else:
        job_id = new_job_id()
        record = _new_job_record(job_id, worker_kind, thread_id, pid, text, affinity_key)
        with _registry_lock:
            _jobs[job_id] = record
            _by_thread.setdefault(thread_id, []).append(job_id)
            _cancel_events[job_id] = threading.Event()
            _resume_events[job_id] = threading.Event()
            _resume_events[job_id].set()

    def _run() -> None:
        with _registry_lock:
            cancel_event = _cancel_events.setdefault(job_id, threading.Event())
            resume_event = _resume_events.setdefault(job_id, threading.Event())

        def checkpoint() -> None:
            control_context = {
                **dispatch_ctx,
                "_job_control": {
                    "cancel_event": cancel_event,
                    "resume_event": resume_event,
                },
            }
            checkpoint_job(control_context)

        output: dict[str, Any] = {}
        try:
            checkpoint()
            sleep_s = _sleep_s()
            sleep_until = time.monotonic() + (sleep_s if worker_kind == "intradoc" else 0)
            while time.monotonic() < sleep_until:
                checkpoint()
                time.sleep(min(0.1, sleep_until - time.monotonic()))
            worker_context = {
                **dispatch_ctx,
                "_job_control": {
                    "cancel_event": cancel_event,
                    "resume_event": resume_event,
                    "checkpoint": checkpoint,
                },
            }
            output = worker_fn(ctx, text, worker_context)
            checkpoint()
            _finish_job(job_id, output, project_id=pid)
        except JobCancelled:
            approval_id = output.get("approval_id")
            if approval_id:
                try:
                    ctx.store.resolve_approval(str(approval_id), "dismiss")
                except Exception:  # noqa: BLE001 - cancellation should still close the job
                    _log.exception("Failed to dismiss approval for cancelled job %s", job_id)
            with _registry_lock:
                job = _jobs.get(job_id)
                if job and job.get("status") != "deleted":
                    job["status"] = "cancelled"
                    job["progress"] = "cancelled by user"
                    snapshot = dict(job)
                else:
                    snapshot = None
            if snapshot:
                from app.agents.session_plane import update_job_record_status

                update_job_record_status(
                    thread_id,
                    job_id,
                    snapshot["status"],
                    snapshot["progress"],
                )
                _publish_job_update(snapshot)
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
