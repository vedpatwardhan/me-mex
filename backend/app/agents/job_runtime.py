"""Foreground/background job ledger for context switch park (04 §12.5)."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

from app.agents.jobs import new_job_id
from app.db import ToolContext

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


def resume_job(job_id: str) -> dict[str, Any] | None:
    with _registry_lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        job["status"] = "running"
        return dict(job)


def _finish_job(job_id: str, output: dict[str, Any]) -> None:
    with _registry_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "awaiting_approval" if output.get("approval_id") else "done"
        job["output"] = output
        job["progress"] = output.get("reply", "")


def start_background_intradoc(
    *,
    thread_id: str,
    ctx: ToolContext,
    text: str,
    context: dict,
    worker_fn: Callable[[ToolContext, str, dict], dict],
) -> dict[str, Any]:
    job_id = new_job_id()
    record: dict[str, Any] = {
        "job_id": job_id,
        "kind": "intradoc",
        "label": (text or "deep read")[:80],
        "status": "running",
        "worker": "intradoc",
        "thread_id": thread_id,
        "progress": "extracting",
    }
    with _registry_lock:
        _jobs[job_id] = record
        _by_thread.setdefault(thread_id, []).append(job_id)

    def _run() -> None:
        sleep_s = _sleep_s()
        if sleep_s:
            time.sleep(sleep_s)
        with _registry_lock:
            st = _jobs.get(job_id, {}).get("status")
        if st == "cancelled":
            return
        try:
            out = worker_fn(ctx, text, context)
            _finish_job(job_id, out)
        except Exception as exc:  # noqa: BLE001
            _finish_job(job_id, {"reply": str(exc), "graph_write": False, "error": True})

    threading.Thread(target=_run, daemon=True).start()
    return dict(record)
