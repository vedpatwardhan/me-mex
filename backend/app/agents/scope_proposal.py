"""P1 scope draft in session checkpoint + dock approval upsert."""

from __future__ import annotations

import time
from typing import Any

from app.db import ToolContext
from app.services.checkpoints import JsonCheckpointStore
from app.tools import dock as dock_tools

_checkpoint = JsonCheckpointStore()


def _checkpoint_for(thread_id: str) -> dict[str, Any]:
    return _checkpoint.load(thread_id) or {}


def load_scope_proposal(thread_id: str) -> dict[str, Any]:
    return dict(_checkpoint_for(thread_id).get("scope_proposal") or {})


def save_scope_proposal(thread_id: str, draft: dict[str, Any]) -> None:
    state = _checkpoint_for(thread_id)
    state["scope_proposal"] = draft
    _checkpoint.save(thread_id, state)


def record_scope_turn(thread_id: str, user_turn: str) -> dict[str, Any]:
    state = _checkpoint_for(thread_id)
    draft = dict(state.get("scope_proposal") or {})
    turns: list[str] = list(draft.get("turns") or [])
    if user_turn.strip():
        turns.append(user_turn.strip()[:2000])
    transcript = [
        {
            "role": str(turn.get("role") or "user"),
            "text": str(turn.get("text") or "")[:2000],
        }
        for turn in (state.get("transcript") or [])[-50:]
        if str(turn.get("text") or "").strip()
    ]
    draft = {
        "turns": turns[-30:],
        "conversation_turns": transcript
        or [{"role": "user", "text": turn} for turn in turns[-30:]],
        "proposed_introduction": draft.get("proposed_introduction", ""),
        "updated_at": time.time(),
    }
    save_scope_proposal(thread_id, draft)
    return draft


def update_scope_proposal(thread_id: str, proposed_introduction: str) -> dict[str, Any]:
    draft = load_scope_proposal(thread_id)
    draft["proposed_introduction"] = proposed_introduction.strip()[:8000]
    draft["updated_at"] = time.time()
    save_scope_proposal(thread_id, draft)
    return draft


def upsert_project_scope_approval(
    ctx: ToolContext,
    *,
    proposed_introduction: str,
    approval_id: str | None = None,
    title: str = "Review project scope",
) -> str:
    payload = {
        "proposed_introduction": proposed_introduction[:8000],
        "draft_version": int(time.time()),
    }
    if approval_id:
        ctx.store.update_pending_approval(
            approval_id,
            title=title,
            payload=payload,
        )
        return approval_id
    return dock_tools.enqueue_pending_approval(
        ctx,
        approval_type="project_scope",
        title=title,
        payload=payload,
    )
