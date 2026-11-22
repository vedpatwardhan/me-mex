"""Session plane: briefing, transcript, observer ingest (04 §12.4)."""

from __future__ import annotations

from typing import Any

from app.agents import job_runtime
from app.agents.briefing import SessionBriefing
from app.agents.context_preprocessor import project_scope_complete
from app.agents.scope_proposal import load_scope_proposal
from app.agents.session_events import publish_session_event
from app.agents.workflow_agent import run_workflow_agent
from app.db import ToolContext, get_store
from app.services.checkpoints import JsonCheckpointStore
from app.tools import dock as dock_tools

_checkpoint = JsonCheckpointStore()


def _checkpoint_for(thread_id: str) -> dict[str, Any]:
    return _checkpoint.load(thread_id) or {}


def append_transcript_turn(thread_id: str, *, role: str, text: str) -> None:
    state = _checkpoint_for(thread_id)
    transcript: list[dict[str, str]] = list(state.get("transcript") or [])
    transcript.append({"role": role, "text": (text or "")[:2000]})
    state["transcript"] = transcript[-50:]
    _checkpoint.save(thread_id, state)


def resolve_job_records(
    thread_id: str,
    job_ids: list[str],
    action: str,
    *,
    approval_id: str | None = None,
) -> None:
    """Persist approval resolution into the checkpoint's job snapshots."""
    state = _checkpoint_for(thread_id)
    ids = set(job_ids)
    jobs = list(state.get("jobs") or [])
    for job in jobs:
        job_approval_id = job.get("approval_id") or job.get("recommendation_id")
        if job.get("job_id") not in ids and job_approval_id != approval_id:
            continue
        job["status"] = {
            "approve": "done",
            "dismiss": "dismissed",
            "cancel": "cancelled",
            "resolved": "resolved",
        }.get(action, "resolved")
        job["approval_resolution"] = action
        job["progress"] = {
            "approve": "approved",
            "dismiss": "dismissed",
            "cancel": "cancelled",
            "resolved": "approval resolved",
        }.get(action, "approval resolved")
    state["jobs"] = jobs[-30:]
    _checkpoint.save(thread_id, state)


def update_job_record_status(
    thread_id: str,
    job_id: str,
    status: str,
    progress: str,
) -> None:
    state = _checkpoint_for(thread_id)
    jobs = list(state.get("jobs") or [])
    for job in jobs:
        if job.get("job_id") == job_id:
            job["status"] = status
            job["progress"] = progress
    state["jobs"] = jobs[-30:]
    _checkpoint.save(thread_id, state)


def remove_job_record(thread_id: str, job_id: str) -> None:
    state = _checkpoint_for(thread_id)
    state["jobs"] = [job for job in (state.get("jobs") or []) if job.get("job_id") != job_id]
    _checkpoint.save(thread_id, state)


def observer_ingest_job(
    *,
    project_id: str,
    thread_id: str,
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> None:
    state = _checkpoint_for(thread_id)
    jobs: list[dict[str, Any]] = list(state.get("jobs") or [])
    jid = job.get("job_id")
    jobs = [j for j in jobs if j.get("job_id") != jid]
    jobs.append(dict(job))
    state["jobs"] = jobs[-30:]
    state["last_worker"] = job.get("worker") or job.get("kind")
    state["last_route"] = job.get("worker") or job.get("kind")
    snippet = (worker_output.get("reply") or "")[:400]
    if snippet:
        state["last_worker_result_snippet"] = snippet

    wa = run_workflow_agent(job=job, worker_output=worker_output)
    state["recommendation_cards"] = wa.get("recommendation_cards") or []
    state["proactive_script"] = wa.get("proactive_script") or ""
    gist_followup = None
    if (
        (job.get("worker") or job.get("kind")) == "gist"
        and job.get("status") in {"done", "awaiting_approval"}
        and (
            worker_output.get("source_summary")
            or worker_output.get("source_error")
            or worker_output.get("error")
        )
    ):
        gist_followup = _compose_gist_followup(job, worker_output)
        state["last_worker_result_snippet"] = gist_followup[:400]
    _checkpoint.save(thread_id, state)

    publish_session_event(
        thread_id,
        {"type": "job_update", "job": job, "source": "observer"},
    )
    if gist_followup:
        append_transcript_turn(thread_id, role="assistant", text=gist_followup)
        publish_session_event(
            thread_id,
            {
                "type": "assistant_followup",
                "job_id": jid,
                "worker": "gist",
                "text": gist_followup,
            },
        )
    proactive = wa.get("proactive_script") or ""
    worker = job.get("worker") or job.get("kind") or ""
    should_proactive = bool(proactive) and (
        (
            job.get("status") == "awaiting_approval"
            and (worker_output.get("approval_id") or job.get("approval_id"))
            and not gist_followup
        )
        or (job.get("status") == "done" and worker != "project_scope" and not gist_followup)
    )
    if should_proactive:
        publish_session_event(
            thread_id,
            {
                "type": "proactive",
                "job_id": jid,
                "text": proactive,
                "recommendation_cards": wa.get("recommendation_cards"),
            },
        )
        publish_session_event(
            thread_id,
            {
                "type": "recommendation",
                "cards": wa.get("recommendation_cards") or [],
            },
        )


def _compose_gist_followup(
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> str:
    """Give a short status acknowledgement; the complete gist lives in dock Review."""
    source_error = str(
        worker_output.get("source_error")
        or ("The source could not be fetched or extracted." if worker_output.get("error") else "")
        or ""
    ).strip()
    if source_error:
        return "I couldn't prepare a reliable gist from that source. Please check the link or share a readable copy."
    if worker_output.get("gist_saved") is True:
        return "The gist is saved to the graph."
    if worker_output.get("approval_id") or job.get("status") == "awaiting_approval":
        return "The gist is ready in the dock for review. Approve it there to add it to the graph."
    return "The gist is ready in the dock for review."


def build_session_briefing(
    *,
    project_id: str,
    thread_id: str,
    include_worker_result: bool = False,
) -> SessionBriefing:
    store = get_store()
    project = store.get_project(project_id)
    ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
    approvals = dock_tools.list_pending_approvals(ctx)
    pending_count = len(approvals.get("items") or [])
    pending_approval_ids = {
        str(item.get("id")) for item in (approvals.get("items") or []) if item.get("id")
    }

    job_runtime.reconcile_pending_approvals(thread_id, pending_approval_ids)
    runtime_jobs = job_runtime.list_jobs(thread_id)
    ckpt = _checkpoint_for(thread_id)
    ckpt_jobs = ckpt.get("jobs") or []
    merged: dict[str, dict[str, Any]] = {}
    for j in ckpt_jobs + runtime_jobs:
        jid = j.get("job_id")
        if jid:
            merged[jid] = dict(j)
    open_jobs = [
        job
        for job in merged.values()
        if job.get("status") in {"running", "paused", "awaiting_approval"}
        and (
            job.get("status") != "awaiting_approval"
            or (job.get("approval_id") or job.get("recommendation_id")) in pending_approval_ids
        )
    ]
    active_job_affinity = sorted(
        {str(job.get("affinity_key")) for job in open_jobs if job.get("affinity_key")}
    )
    active_jobs = [
        {
            key: str(job.get(key) or "")
            for key in ("job_id", "worker", "status", "label")
            if job.get(key) is not None
        }
        for job in open_jobs
    ][:5]
    completed_worker_results: list[dict[str, str]] = []
    for job in reversed(list(merged.values())):
        if job.get("status") not in {"done", "awaiting_approval"}:
            continue
        output = job.get("output") or {}
        result = str(output.get("source_summary") or output.get("summary") or "").strip()
        if not result:
            continue
        completed_worker_results.append(
            {
                "job_id": str(job.get("job_id") or ""),
                "worker": str(job.get("worker") or job.get("kind") or ""),
                "status": str(job.get("status") or "done"),
                "label": str(job.get("label") or "")[:160],
                "source_title": str(output.get("source_title") or "")[:200],
                "source_url": str(output.get("source_url") or "")[:500],
                "result": result[:800],
            }
        )
        if len(completed_worker_results) == 2:
            break

    scope = (project.introduction or "")[:500]
    complete = project_scope_complete(project.introduction)
    draft = load_scope_proposal(thread_id)
    proposal_preview = str(draft.get("proposed_introduction") or "")[:400]
    show_worker_snippet = include_worker_result or complete
    worker_snippet = ""
    if show_worker_snippet:
        worker_snippet = str(ckpt.get("last_worker_result_snippet") or "")[:400]

    briefing: SessionBriefing = {
        "project_scope_snippet": scope,
        "scope_complete": complete,
        "voice_phase": "research" if complete else "p1_scope_onboarding",
        "active_jobs": active_jobs,
        "active_job_affinity": active_job_affinity[-3:],
        "last_route": str(ckpt.get("last_route") or ""),
        "pending_approval_count": pending_count,
        "completed_worker_results": list(reversed(completed_worker_results)),
        "scope_proposal_preview": proposal_preview if not complete else "",
        "worker_result_snippet": worker_snippet,
        "recommendation_cards": list(ckpt.get("recommendation_cards") or []),
        "proactive_script": str(ckpt.get("proactive_script") or ""),
    }
    return briefing
