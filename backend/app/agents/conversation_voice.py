"""Plane 1 conversation stream + optional async dispatch."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.agents import job_runtime
from app.agents.session_plane import append_transcript_turn, build_session_briefing
from app.agents.voice_dispatch import (
    is_voice_turn,
    needs_voice_dispatch,
    resolve_voice_route,
)
from app.agents.worker_registry import worker_handler
from app.config import settings
from app.db import ToolContext, get_store
from app.llm import get_chains

_log = logging.getLogger("memex.v2.voice")


def _conversation_prompt_inputs(
    *,
    text: str,
    briefing: dict[str, Any],
    project_scope: str,
) -> dict[str, Any]:
    briefing_note = json.dumps(briefing, ensure_ascii=False)[:4000]
    scope = project_scope or ""
    augmented = (
        f"[session_briefing]{briefing_note}[/session_briefing]\n"
        f"User: {text}\n"
        "Respond naturally as voice Conversation only (no tools, no graph writes)."
    )
    return {"text": augmented, "project_scope": scope}


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

    briefing = build_session_briefing(project_id=project_id, thread_id=thread_id)

    worker_kind, effective_text, scope_blocked = resolve_voice_route(
        store=store,
        project_id=project_id,
        text=text,
        context_json=ctx_json,
    )
    append_transcript_turn(thread_id, role="user", text=effective_text)
    dispatch = needs_voice_dispatch(
        worker_kind,
        voice_turn=voice,
        text=effective_text,
        scope_blocked=scope_blocked,
    )

    if voice:
        job_runtime.park_active_jobs(thread_id)

    inp = _conversation_prompt_inputs(
        text=effective_text,
        briefing=briefing,
        project_scope=project.introduction or "",
    )
    chains = get_chains()
    if worker_kind == "project_scope" and not dispatch:
        reply = chains.project_scope.invoke(
            {
                "payload": json.dumps(
                    {
                        "current_scope": project.introduction or "",
                        "user_message": effective_text,
                    },
                    ensure_ascii=False,
                ),
            }
        )
    else:
        reply = chains.conversation.invoke(inp)
    if not isinstance(reply, str):
        reply = str(reply)

    chunk_size = max(1, min(32, len(reply) // 8 or 1))
    for i in range(0, len(reply), chunk_size):
        piece = reply[i : i + chunk_size]
        yield {"type": "token", "content": piece, "source": "conversation"}

    append_transcript_turn(thread_id, role="assistant", text=reply)

    job_id: str | None = None
    dispatched_worker: str | None = None
    if dispatch:
        fn = worker_handler(worker_kind)
        if fn:
            ctx = ToolContext(project_id=project_id, thread_id=thread_id, store=store)
            ctx_json_dispatch = {**ctx_json, "voice_dispatch": True}
            job = job_runtime.start_background_worker(
                thread_id=thread_id,
                worker_kind=worker_kind,
                ctx=ctx,
                text=effective_text,
                context=ctx_json_dispatch,
                worker_fn=fn,
                project_id=project_id,
            )
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

    yield {
        "type": "turn_end",
        "reply": reply,
        "graph_write": False,
        "dispatched": bool(job_id),
        "worker_kind": dispatched_worker,
        "job_id": job_id,
        "source": "conversation",
        "details": {
            "worker": "conversation_voice",
            "route": worker_kind,
            "max_tokens_policy": settings.VOICE_FOREGROUND_MAX_TOKENS,
        },
        "jobs": job_runtime.list_jobs(thread_id),
    }
