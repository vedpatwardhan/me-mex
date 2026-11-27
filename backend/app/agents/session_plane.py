"""Session plane: briefing, transcript, observer ingest (04 §12.4)."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Any

from app.agents import job_runtime
from app.agents.briefing import SessionBriefing
from app.agents.context_preprocessor import project_scope_complete
from app.agents.conversation_utterance import (
    UtteranceIntent,
    build_conversation_turn,
    invoke_conversation_utterance,
)
from app.agents.scope_proposal import load_scope_proposal
from app.agents.session_events import publish_session_event
from app.agents.workflow_agent import run_workflow_agent
from app.db import ToolContext, get_store
from app.errors import NotFoundError
from app.services.checkpoints import JsonCheckpointStore
from app.tools import dock as dock_tools

_checkpoint = JsonCheckpointStore()
_checkpoint_lock = threading.RLock()


def _checkpoint_for(thread_id: str) -> dict[str, Any]:
    with _checkpoint_lock:
        return _checkpoint.load(thread_id) or {}


@contextmanager
def _update_checkpoint(thread_id: str):
    with _checkpoint_lock:
        state = _checkpoint_for(thread_id)
        yield state
        _checkpoint.save(thread_id, state)


def append_transcript_turn(thread_id: str, *, role: str, text: str) -> None:
    with _update_checkpoint(thread_id) as state:
        transcript: list[dict[str, str]] = list(state.get("transcript") or [])
        transcript.append({"role": role, "text": (text or "")[:2000]})
        state["transcript"] = transcript[-50:]


def merge_persisted_custom_fields(
    thread_id: str,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge stored URL fields with incoming; persistence happens on turn commit."""
    from app.agents.source_reference import _references_in

    with _checkpoint_lock:
        state = _checkpoint.load(thread_id) or {}
    stored = dict(state.get("persisted_custom_fields") or {})
    inc = dict(incoming or {})
    merged = {**stored, **inc}
    for name, value in inc.items():
        if value is None or value == "":
            merged.pop(name, None)
    url_fields = {
        name: value
        for name, value in merged.items()
        if name != "raw_text" and value is not None and _references_in(str(value))
    }
    return {**url_fields, **{k: v for k, v in inc.items() if k not in url_fields}}


def persisted_url_fields_for_checkpoint(fields: dict[str, Any] | None) -> dict[str, Any]:
    from app.agents.source_reference import _references_in

    return {
        name: value
        for name, value in (fields or {}).items()
        if name != "raw_text" and value is not None and _references_in(str(value))
    }


def build_routing_memory(thread_id: str) -> dict[str, Any]:
    """Return bounded recent dialogue and graph facts for Supervisor coreference."""
    with _checkpoint_lock:
        state = _checkpoint_for(thread_id)
    turns = [
        {
            "role": str(turn.get("role") or ""),
            "text": str(turn.get("text") or "")[:500],
        }
        for turn in (state.get("transcript") or [])[-6:]
        if turn.get("role") in {"user", "assistant"} and turn.get("text")
    ]
    graph_changes = list(state.get("recent_graph_changes") or [])[-4:]
    focus_root = next(
        (
            node
            for change in reversed(graph_changes)
            for node in reversed(change.get("nodes", []))
            if node.get("node_kind") == "ROOT"
        ),
        None,
    )
    summary = "; ".join(
        f"{change.get('operation', 'updated')} {node.get('node_kind', 'node')} "
        f"'{node.get('title', '')}' (id={node.get('id')})"
        for change in graph_changes
        for node in change.get("nodes", [])
    )
    return {
        "summary": summary[:1200],
        "recent_graph_changes": graph_changes,
        "recent_turns": turns,
        "focus_root": focus_root,
        "current_source": state.get("current_source"),
    }


def record_routing_source(
    thread_id: str,
    *,
    worker: str,
    source_url: str | None,
    title: str | None = None,
    root_id: str | None = None,
) -> None:
    """Remember the source currently being processed, including whether it has a ROOT."""
    with _update_checkpoint(thread_id) as state:
        state["current_source"] = {
            "worker": worker,
            "source_url": source_url or "",
            "title": (title or "")[:180],
            "root_id": root_id or "",
        }


def record_recent_graph_change(
    *,
    store,
    project_id: str,
    thread_id: str,
    operation: str,
    payload: dict[str, Any] | None,
    result: dict[str, Any],
) -> None:
    """Persist exact graph node references from an approved graph change."""
    payload = payload or {}
    node_ids: list[str] = []
    if operation == "placement":
        node_ids.extend([payload.get("root_id"), *(result.get("edges") or [])])
    else:
        created = result.get("result") or result
        root_id = created.get("root_id")
        if root_id:
            node_ids.append(root_id)
        node_ids.extend(created.get("node_ids") or [])
        node_ids.extend(created.get("concept_ids") or [])
        node_ids.extend(
            created.get(key)
            for key in ("node_id", "parent_id", "new_hub_id", "merged_into", "target_id")
            if created.get(key)
        )

    nodes: list[dict[str, str]] = []
    seen: set[str] = set()
    for node_id in node_ids:
        if not node_id or str(node_id) in seen:
            continue
        seen.add(str(node_id))
        try:
            node = store.get_node(str(node_id))
        except NotFoundError:  # Stale/deleted graph references should not break approval.
            continue
        if node.project_id != project_id:
            continue
        node_record = {"id": node.id, "title": node.title[:180], "node_kind": node.node_kind.value}
        if node.node_kind.value == "ROOT" and node.source_uri:
            node_record["source_uri"] = node.source_uri
        nodes.append(node_record)
        if len(nodes) == 8:
            break
    if not nodes:
        return

    with _update_checkpoint(thread_id) as state:
        changes = list(state.get("recent_graph_changes") or [])
        changes.append({"operation": operation, "nodes": nodes})
        state["recent_graph_changes"] = changes[-4:]
        current_source = state.get("current_source") or {}
        for node in nodes:
            if (
                node.get("node_kind") == "ROOT"
                and not current_source.get("root_id")
                and (
                    node.get("source_uri") == current_source.get("source_url")
                    or (
                        not current_source.get("source_url")
                        and operation in {"gist_root", "gist", "intradoc", "intra_doc_staging"}
                    )
                )
            ):
                current_source["root_id"] = node["id"]
                current_source["title"] = node["title"]
                state["current_source"] = current_source


def resolve_job_records(
    thread_id: str,
    job_ids: list[str],
    action: str,
    *,
    approval_id: str | None = None,
) -> None:
    """Persist approval resolution into the checkpoint's job snapshots."""
    with _update_checkpoint(thread_id) as state:
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
        history: dict[str, dict[str, Any]] = dict(state.get("job_history") or {})
        for job in jobs:
            jid = str(job.get("job_id") or "")
            job_approval_id = job.get("approval_id") or job.get("recommendation_id")
            if jid not in ids and job_approval_id != approval_id:
                continue
            row = dict(history.get(jid) or {})
            if not row and jid:
                row = {"job_id": jid}
            row["status"] = job["status"]
            row["output_summary"] = str(job.get("progress") or row.get("output_summary") or "")[
                :800
            ]
            if jid:
                history[jid] = row
        state["job_history"] = history


def update_job_record_status(
    thread_id: str,
    job_id: str,
    status: str,
    progress: str,
) -> None:
    with _update_checkpoint(thread_id) as state:
        jobs = list(state.get("jobs") or [])
        for job in jobs:
            if job.get("job_id") == job_id:
                job["status"] = status
                job["progress"] = progress
        state["jobs"] = jobs[-30:]


def remove_job_record(thread_id: str, job_id: str) -> None:
    with _update_checkpoint(thread_id) as state:
        state["jobs"] = [job for job in (state.get("jobs") or []) if job.get("job_id") != job_id]


def _observer_conversation_line(
    *,
    project_id: str,
    thread_id: str,
    intent: UtteranceIntent,
    utterance_facts: dict[str, Any],
    user_message: str = "",
) -> str:
    store = get_store()
    project = store.get_project(project_id)
    briefing = build_session_briefing(project_id=project_id, thread_id=thread_id)
    inp = build_conversation_turn(
        intent=intent,
        user_message=user_message or "Status update for the user.",
        briefing=briefing,
        project_scope=project.introduction or "",
        user_fields=None,
        utterance_facts=utterance_facts,
    )
    return invoke_conversation_utterance(inp, intent=intent)


def _gist_followup_utterance(
    *,
    project_id: str,
    thread_id: str,
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> str:
    source_error = str(
        worker_output.get("source_error")
        or ("fetch_failed" if worker_output.get("error") else "")
        or ""
    ).strip()
    facts: dict[str, Any] = {
        "worker": "gist",
        "job_id": job.get("job_id"),
        "job_status": job.get("status"),
        "gist_saved": bool(worker_output.get("gist_saved")),
        "awaiting_approval": bool(
            worker_output.get("approval_id") or job.get("status") == "awaiting_approval"
        ),
        "source_error": source_error or None,
    }
    return _observer_conversation_line(
        project_id=project_id,
        thread_id=thread_id,
        intent=UtteranceIntent.GIST_FOLLOWUP,
        utterance_facts=facts,
    )


def _proactive_utterance(
    *,
    project_id: str,
    thread_id: str,
    meta: dict[str, Any],
) -> str:
    kind = meta.get("kind")
    if kind == "review":
        intent = UtteranceIntent.PROACTIVE_REVIEW
    elif kind == "complete":
        intent = UtteranceIntent.PROACTIVE_COMPLETE
    else:
        return ""
    return _observer_conversation_line(
        project_id=project_id,
        thread_id=thread_id,
        intent=intent,
        utterance_facts=meta,
    )


def observer_ingest_job(
    *,
    project_id: str,
    thread_id: str,
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> None:
    jid = job.get("job_id")
    snippet = (worker_output.get("reply") or "")[:400]
    wa = run_workflow_agent(job=job, worker_output=worker_output)
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
        gist_followup = _gist_followup_utterance(
            project_id=project_id,
            thread_id=thread_id,
            job=job,
            worker_output=worker_output,
        )
    with _update_checkpoint(thread_id) as state:
        jobs: list[dict[str, Any]] = list(state.get("jobs") or [])
        jobs = [j for j in jobs if j.get("job_id") != jid]
        jobs.append(dict(job))
        state["jobs"] = jobs[-30:]
        state["last_worker"] = job.get("worker") or job.get("kind")
        state["last_route"] = job.get("worker") or job.get("kind")
        if snippet:
            state["last_worker_result_snippet"] = snippet
        state["recommendation_cards"] = wa.get("recommendation_cards") or []
        state["proactive_script"] = wa.get("proactive_script") or ""
        if gist_followup:
            state["last_worker_result_snippet"] = gist_followup[:400]

    if job.get("status") == "done" and worker_output.get("graph_write"):
        record_recent_graph_change(
            store=get_store(),
            project_id=project_id,
            thread_id=thread_id,
            operation=str(job.get("worker") or job.get("kind") or "graph_update"),
            payload=worker_output.get("payload"),
            result=worker_output,
        )

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
    proactive_meta = wa.get("proactive_meta")
    worker = job.get("worker") or job.get("kind") or ""
    should_proactive = bool(proactive_meta) and (
        (
            job.get("status") == "awaiting_approval"
            and (worker_output.get("approval_id") or job.get("approval_id"))
            and not gist_followup
        )
        or (job.get("status") == "done" and worker != "project_scope" and not gist_followup)
    )
    if should_proactive:
        proactive = _proactive_utterance(
            project_id=project_id,
            thread_id=thread_id,
            meta=proactive_meta or {},
        )
        state_proactive = proactive or ""
        with _update_checkpoint(thread_id) as state:
            state["proactive_script"] = state_proactive[:512]
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

    history_rows = list(reversed(list_job_history(thread_id)))[:15]
    recent_jobs: list[dict[str, str]] = []
    for row in history_rows:
        item = {
            key: str(row.get(key) or "")
            for key in (
                "job_id",
                "worker",
                "status",
                "label",
                "source_url",
                "source_title",
                "output_summary",
            )
            if row.get(key) is not None
        }
        if (
            complete
            and item.get("worker") == "project_scope"
            and item.get("status") == "awaiting_approval"
            and pending_count == 0
        ):
            item["status"] = "done"
            item["output_summary"] = item.get("output_summary") or "Project scope approved."
        recent_jobs.append(item)

    briefing: SessionBriefing = {
        "project_scope_snippet": scope,
        "scope_complete": complete,
        "voice_phase": "research" if complete else "p1_scope_onboarding",
        "active_jobs": active_jobs,
        "recent_jobs": recent_jobs,
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


def upsert_job_history(thread_id: str, job: dict[str, Any]) -> None:
    """Append-only job run ledger for history UI and status answers."""
    jid = job.get("job_id")
    if not jid:
        return
    output = job.get("output") or {}
    summary = str(
        output.get("source_summary")
        or output.get("summary")
        or output.get("reply")
        or job.get("progress")
        or ""
    ).strip()[:800]
    row = {
        "job_id": str(jid),
        "parent_turn_id": str(job.get("parent_turn_id") or ""),
        "worker": str(job.get("worker") or job.get("kind") or ""),
        "status": str(job.get("status") or "running"),
        "label": str(job.get("label") or "")[:160],
        "source_url": str(output.get("source_url") or "")[:500],
        "source_title": str(output.get("source_title") or "")[:200],
        "output_summary": summary,
        "approval_id": str(job.get("approval_id") or job.get("recommendation_id") or ""),
        "updated_at": time.time(),
        "reverted_at": job.get("reverted_at"),
    }
    with _update_checkpoint(thread_id) as state:
        history: dict[str, dict[str, Any]] = dict(state.get("job_history") or {})
        prev = history.get(str(jid)) or {}
        if prev.get("created_at"):
            row["created_at"] = prev["created_at"]
        else:
            row["created_at"] = time.time()
        history[str(jid)] = {**prev, **row}
        state["job_history"] = history


def mark_job_history_reverted(thread_id: str, job_id: str) -> None:
    with _update_checkpoint(thread_id) as state:
        history: dict[str, dict[str, Any]] = dict(state.get("job_history") or {})
        row = history.get(job_id)
        if not row:
            return
        row["reverted_at"] = time.time()
        row["status"] = "superseded_by_revert"
        history[job_id] = row
        state["job_history"] = history


def list_job_history(thread_id: str) -> list[dict[str, Any]]:
    ckpt = _checkpoint_for(thread_id)
    history = ckpt.get("job_history") or {}
    items = list(history.values())
    items.sort(key=lambda r: float(r.get("updated_at") or r.get("created_at") or 0))
    return items
