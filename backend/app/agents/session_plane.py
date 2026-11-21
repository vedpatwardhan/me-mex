"""Session plane: briefing, transcript, observer ingest (04 §12.4)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agents import job_runtime
from app.agents.briefing import SessionBriefing
from app.agents.context_preprocessor import project_scope_complete
from app.agents.scope_proposal import load_scope_proposal
from app.agents.session_events import publish_session_event
from app.agents.workflow_agent import run_workflow_agent
from app.db import ToolContext, get_store
from app.llm import get_chains
from app.services.checkpoints import JsonCheckpointStore
from app.tools import dock as dock_tools

_checkpoint = JsonCheckpointStore()
_log = logging.getLogger("memex.v2.session")


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
    gist_followup = None
    if (
        (job.get("worker") or job.get("kind")) == "gist"
        and job.get("status") == "done"
        and (
            worker_output.get("source_summary")
            or worker_output.get("source_error")
            or worker_output.get("error")
        )
    ):
        gist_followup = _compose_gist_followup(project_id, job, worker_output)
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
    project_id: str,
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> str:
    """Turn a completed, source-grounded gist (or fetch error) into the user reply."""
    store = get_store()
    project = store.get_project(project_id)
    source_summary = str(worker_output.get("source_summary") or "").strip()
    source_error = str(
        worker_output.get("source_error")
        or (
            "The source could not be fetched or extracted."
            if worker_output.get("error")
            else worker_output.get("reply")
        )
        or ""
    ).strip()
    payload = {
        "user_request": job.get("request_text") or job.get("label") or "Summarize the source.",
        "source_title": worker_output.get("source_title") or "",
        "source_url": worker_output.get("source_url") or "",
        "source_summary": source_summary,
        "source_error": source_error if not source_summary else "",
        "gist_saved": worker_output.get("gist_saved") is True,
    }
    instruction = (
        "A background source-gist job has finished. Give the user a concise, natural answer "
        "to their original request using only the worker's source_summary. Paraphrase it in "
        "2–4 short sentences, avoid verbatim quotes, and do not add facts from memory. "
        "If gist_saved is true, briefly confirm it was saved; otherwise do not imply persistence. "
        "If source_error is present and source_summary is empty, explain briefly that the "
        "source could not be read and ask for a readable link or excerpt. Do not imply an "
        "error case has a summary. Completed worker result:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        reply = get_chains().conversation.invoke(
            {"text": instruction, "project_scope": project.introduction or ""}
        )
        text = str(reply or "").strip()
        if text:
            return text
    except Exception as exc:  # noqa: BLE001 - fall back to the worker's grounded summary
        _log.warning("gist follow-up generation failed; using worker summary: %s", exc)
    if source_summary:
        title = str(worker_output.get("source_title") or "the source")
        return f"Here's a concise summary of {title}: {source_summary}"
    return source_error or "I couldn't read the source. Please share a readable link or excerpt."


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
    show_worker_snippet = include_worker_result or complete
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
