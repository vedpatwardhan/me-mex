"""Plane 1 conversation stream + optional async dispatch."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agents import job_runtime
from app.agents.context_preprocessor import graph_candidates_for_supervisor
from app.agents.job_affinity import resolve_job_dispatch
from app.agents.session_plane import (
    append_transcript_turn,
    build_routing_memory,
    build_session_briefing,
    record_routing_source,
)
from app.agents.source_reference import resolve_source_reference
from app.agents.voice_dispatch import (
    is_voice_turn,
    needs_voice_dispatch,
    resolve_voice_route_async,
)
from app.agents.worker_registry import worker_handler
from app.config import settings
from app.db import ToolContext, get_store
from app.llm import get_chains
from app.prompts import load_prompt
from app.services.llm_gateway import llm_gateway

_log = logging.getLogger("memex.v2.voice")


def _conversation_prompt_inputs(
    *,
    text: str,
    briefing: dict[str, Any],
    project_scope: str,
    user_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conversation_briefing = {
        key: briefing.get(key)
        for key in (
            "project_scope_snippet",
            "scope_complete",
            "completed_worker_results",
            "active_jobs",
            "pending_approval_count",
            "scope_proposal_preview",
        )
        if briefing.get(key) not in (None, [], "")
    }
    briefing_note = json.dumps(conversation_briefing, ensure_ascii=False)[:4000]
    scope = project_scope or ""
    safe_user_fields = {
        str(key): str(value)[:1200]
        for key, value in (user_fields or {}).items()
        if value is not None
        and not (
            (reference := resolve_source_reference("", {str(key): value})).url or reference.error
        )
    }
    augmented = (
        f"[session_briefing]{briefing_note}[/session_briefing]\n"
        f"[user_provided_fields]{json.dumps(safe_user_fields, ensure_ascii=False)}"
        "[/user_provided_fields]\n"
        f"User: {text}\n"
        "Respond naturally as voice Conversation only (no tools, no graph writes)."
    )
    return {"text": augmented, "project_scope": scope}


def _background_worker_acknowledgement(worker_kind: str, *, already_running: bool = False) -> str:
    """Short, factual interim response; dispatch turns do not ask Conversation to speculate."""
    if already_running:
        return "That job is still running. I’ll share its result in the dock when it’s ready."
    acknowledgements = {
        "gist": "I’ll read the paper you shared and put a concise gist in the dock for review.",
        "intradoc": "I’ll analyze the source and put the results in the dock for review.",
        "project_scope": "I’ll prepare the scope proposal and put it in the dock for review.",
        "link": "I’ll prepare placement options and put them in the dock for review.",
        "reorg": "I’ll prepare a reorganization proposal for review in the dock.",
        "retrieval": "I’ll check the graph and highlight relevant nodes.",
    }
    return acknowledgements.get(worker_kind, "I’ll work on that and share the result in the dock.")


def _conversation_openai_messages(inp: dict[str, Any]) -> list[dict[str, Any]]:
    system = load_prompt("conversation", project_scope=inp.get("project_scope") or "")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": inp["text"]},
    ]


async def _astream_voice_conversation_reply(
    inp: dict[str, Any],
) -> AsyncIterator[str]:
    """Stream conversation tokens (plane 1 TTS source)."""
    if settings.CHAT_LLM_MODE != "live":
        chains = get_chains()
        reply = chains.conversation.invoke(inp)
        if not isinstance(reply, str):
            reply = str(reply)
        step = max(1, min(32, len(reply) // 4 or 1))
        for i in range(0, len(reply), step):
            yield reply[i : i + step]
        return

    messages = _conversation_openai_messages(inp)
    async for piece in llm_gateway.stream_chat_completion(
        messages,
        max_tokens=settings.VOICE_FOREGROUND_MAX_TOKENS,
        enable_reasoning=False,
        caller="Conversation",
    ):
        if piece:
            yield piece


async def astream_conversation_voice(
    *,
    project_id: str,
    thread_id: str,
    text: str,
    context_json: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    ctx_json = dict(context_json or {})
    voice = is_voice_turn(ctx_json)
    _log.info(
        "conversation_stream thread_id=%s project_id=%s voice_turn=%s text_len=%d",
        thread_id,
        project_id,
        voice,
        len(text or ""),
    )
    store = get_store()
    project = store.get_project(project_id)
    briefing = build_session_briefing(
        project_id=project_id,
        thread_id=thread_id,
    )
    routing_context = {
        **ctx_json,
        "graph_candidates": graph_candidates_for_supervisor(store, project_id),
        "routing_memory": build_routing_memory(thread_id),
        "session_state": {
            "active_jobs": [
                {
                    key: job.get(key)
                    for key in ("job_id", "worker", "status", "label")
                    if job.get(key) is not None
                }
                for job in (briefing.get("active_jobs") or [])
            ],
            "pending_approval_count": briefing.get("pending_approval_count") or 0,
            "completed_worker_results": briefing.get("completed_worker_results") or [],
        },
    }

    decision, effective_text, scope_blocked = await resolve_voice_route_async(
        store=store,
        project_id=project_id,
        thread_id=thread_id,
        text=text,
        context_json=routing_context,
    )
    worker_kind = decision.worker
    if worker_kind == "job_control":
        from app.agents.workers import job_control_worker

        ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
        control_context = {
            **routing_context,
            "supervisor_decision": decision.model_dump(),
        }
        result = job_control_worker(ctx, effective_text, control_context)
        reply = str(result.get("reply") or "I couldn't apply that job action.")
        append_transcript_turn(thread_id, role="user", text=effective_text)
        append_transcript_turn(thread_id, role="assistant", text=reply)
        for i in range(0, len(reply), 32):
            yield {"type": "token", "content": reply[i : i + 32], "source": "conversation"}
        yield {
            "type": "turn_end",
            "worker": "job_control",
            "reply": reply,
            "graph_write": False,
            "dispatched": False,
            "worker_kind": "job_control",
            "details": result,
            "jobs": [
                job
                for job in job_runtime.list_jobs(thread_id)
                if job.get("status") in {"running", "paused", "awaiting_approval"}
            ],
        }
        return
    if decision.source_error == "link_resolution":
        reply = str(decision.content or "Please clarify which ROOT and destination node to link.")
        append_transcript_turn(thread_id, role="user", text=effective_text)
        append_transcript_turn(thread_id, role="assistant", text=reply)
        for i in range(0, len(reply), 32):
            yield {"type": "token", "content": reply[i : i + 32], "source": "conversation"}
        yield {
            "type": "turn_end",
            "reply": reply,
            "graph_write": False,
            "dispatched": False,
            "worker_kind": "conversation",
            "details": {"route": "link_clarification"},
            "jobs": job_runtime.list_jobs(thread_id),
        }
        return
    if decision.intent == "status" and not briefing.get("worker_result_snippet"):
        briefing = build_session_briefing(
            project_id=project_id,
            thread_id=thread_id,
            include_worker_result=True,
        )
    append_transcript_turn(thread_id, role="user", text=effective_text)
    dispatch = needs_voice_dispatch(
        decision,
        voice_turn=voice,
        scope_blocked=scope_blocked,
    )
    if dispatch and worker_kind in {"gist", "intradoc"}:
        fields = routing_context.get("custom_fields") or {}
        selected_roots = [
            node_id
            for node_id in routing_context.get("selected_node_ids") or []
            if any(
                node.get("id") == node_id and node.get("node_kind") == "ROOT"
                for node in routing_context.get("graph_candidates") or []
            )
        ]
        source = resolve_source_reference(
            effective_text,
            fields,
            selected_reference=decision.source_reference,
            selected_field=decision.source_field,
        )
        existing_source_root = next(
            (
                node.id
                for node in store.list_nodes(project_id)
                if source.url and node.node_kind.value == "ROOT" and node.source_uri == source.url
            ),
            None,
        )
        record_routing_source(
            thread_id,
            worker=worker_kind,
            source_url=source.url,
            title=decision.title or fields.get("title"),
            root_id=(
                fields.get("root_id")
                or (selected_roots[0] if len(selected_roots) == 1 else None)
                or existing_source_root
            ),
        )
    plan = resolve_job_dispatch(
        thread_id=thread_id,
        project_id=project_id,
        worker_kind=worker_kind,
        effective_text=effective_text,
        context_json={**routing_context, "supervisor_decision": decision.model_dump()},
        jobs=job_runtime.list_jobs(thread_id),
        pending_approvals=store.list_pending(project_id, thread_id),
        introduction=project.introduction or "",
        dispatch_allowed=dispatch,
    )
    worker_fn = worker_handler(worker_kind) if dispatch and plan.action != "skip" else None
    already_running = dispatch and plan.reason == "already_running"
    dispatch_pending = bool(worker_fn) or already_running

    tokens: list[str] = []
    if dispatch_pending:
        reply_parts = _background_worker_acknowledgement(
            worker_kind,
            already_running=already_running,
        )
        for i in range(0, len(reply_parts), 32):
            piece = reply_parts[i : i + 32]
            tokens.append(piece)
            yield {"type": "token", "content": piece, "source": "conversation"}
    else:
        if decision.reply:
            for i in range(0, len(decision.reply), 32):
                piece = decision.reply[i : i + 32]
                tokens.append(piece)
                yield {"type": "token", "content": piece, "source": "conversation"}
        else:
            inp = _conversation_prompt_inputs(
                text=text,
                briefing=briefing,
                project_scope=project.introduction or "",
                user_fields=ctx_json.get("custom_fields") or {},
            )
            async for piece in _astream_voice_conversation_reply(inp):
                tokens.append(piece)
                yield {"type": "token", "content": piece, "source": "conversation"}

    reply = "".join(tokens)

    append_transcript_turn(thread_id, role="assistant", text=reply)

    job_id: str | None = None
    dispatched_worker: str | None = None
    if dispatch_pending and worker_fn:
        ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
        ctx_json_dispatch = {
            **routing_context,
            "voice_dispatch": True,
            "supervisor_decision": decision.model_dump(),
        }
        job = job_runtime.dispatch_background_worker(
            thread_id=thread_id,
            worker_kind=worker_kind,
            ctx=ctx,
            text=effective_text,
            context=ctx_json_dispatch,
            worker_fn=worker_fn,
            project_id=project_id,
            plan=plan,
        )
        if not job:
            dispatch = False
        else:
            job_id = job.get("job_id")
            dispatched_worker = worker_kind
        _log.info(
            "voice_dispatch job_id=%s worker=%s thread_id=%s project_id=%s",
            job_id,
            worker_kind,
            thread_id,
            project_id,
        )
        yield {
            "type": "custom",
            "job": job,
            "source": "dispatch",
        }

    jobs = [
        job
        for job in job_runtime.list_jobs(thread_id)
        if job.get("status") in {"running", "paused", "awaiting_approval"}
    ]
    approval_id = None
    for j in jobs:
        if j.get("status") != "awaiting_approval":
            continue
        aid = j.get("approval_id") or (j.get("output") or {}).get("approval_id")
        if aid:
            approval_id = aid
            break
    details = {
        "worker": "conversation_voice",
        "route": worker_kind,
        "max_tokens_policy": settings.VOICE_FOREGROUND_MAX_TOKENS,
    }
    if approval_id:
        details["approval_id"] = approval_id

    yield {
        "type": "turn_end",
        "reply": reply,
        "graph_write": False,
        "dispatched": bool(job_id),
        "worker_kind": dispatched_worker,
        "job_id": job_id,
        "source": "conversation",
        "details": details,
        "jobs": jobs,
    }
