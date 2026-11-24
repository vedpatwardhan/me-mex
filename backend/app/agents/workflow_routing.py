"""Workflow-phase routing guardrails (post-scope next steps, etc.)."""

from __future__ import annotations

import re

from app.llm.schemas import WorkerRoute

_WORKFLOW_NEXT_STEPS = re.compile(
    r"\b(?:what(?:'s| is) next|next steps?|proceed|move forward|get started|how (?:do|should) (?:we|i) start|"
    r"what (?:should|do) (?:we|i) do (?:now|next)|where (?:do|should) (?:we|i) (?:go|start)|"
    r"what comes next|after (?:the )?scope)\b",
    re.IGNORECASE,
)

_SCOPE_REVIEW_REDIRECT = re.compile(
    r"\b(?:review (?:the )?scope|explore.{0,40}scope|proposed scope|adjustments? to (?:the )?scope|"
    r"ready for review in the dock)\b",
    re.IGNORECASE,
)


def is_workflow_next_steps_inquiry(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    return bool(_WORKFLOW_NEXT_STEPS.search(stripped))


def supervisor_reply_redirects_to_scope_review(reply: str | None) -> bool:
    if not reply:
        return False
    return bool(_SCOPE_REVIEW_REDIRECT.search(reply))


def normalize_post_scope_workflow_decision(
    decision: WorkerRoute,
    text: str,
    *,
    scope_complete: bool,
) -> WorkerRoute:
    """When scope is committed, 'what's next' must not reuse a scope-review supervisor reply."""
    if not scope_complete or not is_workflow_next_steps_inquiry(text):
        return decision
    if decision.worker == "project_scope" and decision.dispatch:
        return decision
    needs_conversation_llm = (
        decision.reply is None
        or supervisor_reply_redirects_to_scope_review(decision.reply)
        or decision.intent in {"status", "scope_conversation", "scope_save"}
    )
    if not needs_conversation_llm:
        return decision
    return decision.model_copy(
        update={
            "worker": "conversation",
            "intent": "conversation",
            "dispatch": False,
            "reply": None,
            "job_action": None,
        }
    )
