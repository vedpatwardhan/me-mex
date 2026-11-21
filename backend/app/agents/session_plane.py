"""Session plane: briefing, transcript, observer ingest (04 §12.4)."""

from __future__ import annotations

from typing import Any

from app.agents import job_runtime
from app.agents.briefing import SessionBriefing
from app.agents.context_preprocessor import project_scope_complete
from app.agents.scope_proposal import load_scope_proposal
from app.agents.session_events import publish_session_event
from app.agents.voice_dialogue import user_asked_for_status
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
    _checkpoint.save(thread_id, state)

    publish_session_event(
        thread_id,
        {"type": "job_update", "job": job, "source": "observer"},
    )
    proactive = wa.get("proactive_script") or ""
    worker = job.get("worker") or job.get("kind") or ""
    should_proactive = bool(proactive) and (
        (
            job.get("status") == "awaiting_approval"
            and (worker_output.get("approval_id") or job.get("approval_id"))
        )
        or (job.get("status") == "done" and worker != "project_scope")
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


def build_session_briefing(
    *,
    project_id: str,
    thread_id: str,
    user_text: str = "",
) -> SessionBriefing:
    store = get_store()
    project = store.get_project(project_id)
    ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
    approvals = dock_tools.list_pending_approvals(ctx)
    pending_count = len(approvals.get("items") or [])

    runtime_jobs = job_runtime.list_jobs(thread_id)
    ckpt = _checkpoint_for(thread_id)
    ckpt_jobs = ckpt.get("jobs") or []
    merged: dict[str, dict[str, Any]] = {}
    for j in ckpt_jobs + runtime_jobs:
        jid = j.get("job_id")
        if jid:
            merged[jid] = dict(j)
    active_jobs = list(merged.values())

    scope = (project.introduction or "")[:500]
    complete = project_scope_complete(project.introduction)
    draft = load_scope_proposal(thread_id)
    proposal_preview = str(draft.get("proposed_introduction") or "")[:400]
    show_worker_snippet = user_asked_for_status(user_text) or complete
    worker_snippet = ""
    if show_worker_snippet:
        worker_snippet = str(ckpt.get("last_worker_result_snippet") or "")[:400]

    affinity_keys = sorted(
        {str(j.get("affinity_key")) for j in active_jobs if j.get("affinity_key")}
    )
    briefing: SessionBriefing = {
        "project_scope_snippet": scope,
        "scope_complete": complete,
        "voice_phase": "research" if complete else "p1_scope_onboarding",
        "active_jobs": active_jobs,
        "active_job_affinity": affinity_keys[-3:],
        "last_route": str(ckpt.get("last_route") or ""),
        "pending_approval_count": pending_count,
        "scope_proposal_preview": proposal_preview if not complete else "",
        "worker_result_snippet": worker_snippet,
        "recommendation_cards": list(ckpt.get("recommendation_cards") or []),
        "proactive_script": str(ckpt.get("proactive_script") or ""),
    }
    return briefing
