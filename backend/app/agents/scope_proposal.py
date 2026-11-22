"""P1 scope draft in session checkpoint + dock approval upsert."""

from __future__ import annotations

import json
import time
from typing import Any

from app.db import ToolContext
from app.llm.schemas import ProjectScopeResult
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


def latest_pending_scope_proposal(ctx: ToolContext) -> str:
    """Most recent open project_scope approval text for this thread (if any)."""
    for item in reversed(ctx.store.list_pending(ctx.project_id, ctx.thread_id)):
        if item.approval_type != "project_scope":
            continue
        intro = str((item.payload or {}).get("proposed_introduction") or "").strip()
        if intro:
            return intro
    return ""


def build_project_scope_llm_payload(
    ctx: ToolContext,
    text: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inputs for ProjectScope chain to classify revision mode and draft the proposal."""
    draft = record_scope_turn(ctx.thread_id, text)
    proj = ctx.store.get_project(ctx.project_id)
    committed = (proj.introduction or "").strip()
    pending = latest_pending_scope_proposal(ctx)
    draft_text = str(draft.get("proposed_introduction") or "").strip()

    # The open review is the active working baseline. If there is no open
    # proposal, use saved scope before a stale session draft.
    if pending:
        baseline = pending
    elif committed:
        baseline = committed
    else:
        baseline = draft_text

    if baseline and draft_text != baseline:
        update_scope_proposal(ctx.thread_id, baseline)
        draft_text = baseline

    decision = (context or {}).get("supervisor_decision") or {}
    supervisor_candidate = str(decision.get("content") or "").strip()
    fields = (context or {}).get("custom_fields") or {}
    force_replace = fields.get("force_scope_rewrite") is True or str(
        fields.get("force_scope_rewrite") or ""
    ).lower() in ("1", "true", "yes")

    return {
        "committed_scope": committed,
        "baseline_proposal": baseline,
        "supervisor_candidate": supervisor_candidate,
        "current_scope": committed,
        "latest_user_message": text,
        "draft_proposal": draft_text,
        "conversation_turns": draft.get("conversation_turns", []),
        "force_scope_rewrite": force_replace,
        "pending_scope_approval": bool(pending),
    }


def project_scope_payload_json(
    ctx: ToolContext,
    text: str,
    *,
    context: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        build_project_scope_llm_payload(ctx, text, context=context),
        ensure_ascii=False,
    )


def normalize_scope_result(raw_result: Any, payload: dict[str, Any]) -> ProjectScopeResult:
    """Validate ProjectScope output and enforce safe revision-mode fallbacks."""
    if isinstance(raw_result, ProjectScopeResult):
        result = raw_result
    elif isinstance(raw_result, dict):
        result = ProjectScopeResult.model_validate(raw_result)
    else:
        result = ProjectScopeResult(
            revision_mode="incremental" if payload.get("baseline_proposal") else "replace",
            proposed_introduction=str(raw_result or "").strip(),
        )

    if payload.get("force_scope_rewrite") or not payload.get("baseline_proposal"):
        return result.model_copy(update={"revision_mode": "replace"})
    return result


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
