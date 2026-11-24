"""Deterministic guardrails for job status vs job_control Supervisor mistakes."""

from __future__ import annotations

import re

from app.llm.schemas import WorkerRoute

_CONTROL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bpause\b|\bhold\b|\bsuspend\b", re.IGNORECASE), "pause"),
    (re.compile(r"\bresume\b|\bunpause\b|\bcontinue\b", re.IGNORECASE), "resume"),
    (re.compile(r"\bcancel\b|\babort\b", re.IGNORECASE), "cancel"),
    (re.compile(r"\bdelete\b|\bremove\b|\bdiscard\b", re.IGNORECASE), "delete"),
    (re.compile(r"\bstop\b", re.IGNORECASE), "cancel"),
)

_STATUS_PATTERN = re.compile(
    r"\bstatus\b|\bprogress\b|\bhow far\b|\bstill running\b|\bdone yet\b|"
    r"\bstatus check\b|\bstate of\b|\bwhat(?:'s| is) the status\b|\bcheck on\b",
    re.IGNORECASE,
)

_APPROVAL_PATTERN = re.compile(r"\bapprove\b|\bdismiss\b|\breject\b", re.IGNORECASE)


def detect_job_control_verb(text: str) -> str | None:
    """Return job_action when the user explicitly asked to control a job."""
    stripped = text.strip()
    if not stripped:
        return None
    for pattern, action in _CONTROL_PATTERNS:
        if pattern.search(stripped):
            return action
    return None


def is_job_status_inquiry(text: str) -> bool:
    """True when the user is asking about job state, not changing it."""
    stripped = text.strip()
    if not stripped:
        return False
    if not _STATUS_PATTERN.search(stripped):
        return False
    return detect_job_control_verb(stripped) is None


def is_approval_utterance(text: str) -> bool:
    """Dock HITL approve/dismiss — not job_control."""
    stripped = text.strip()
    if not stripped:
        return False
    if not _APPROVAL_PATTERN.search(stripped):
        return False
    if re.search(r"\b(job|queue|background)\b", stripped, re.IGNORECASE):
        return False
    return detect_job_control_verb(stripped) is None


def normalize_job_control_decision(decision: WorkerRoute, text: str) -> WorkerRoute:
    """Rewrite mistaken job_control (e.g. pause on status check) to conversation/status."""
    if decision.worker != "job_control" or decision.intent != "job_control":
        if is_job_status_inquiry(text) and decision.intent != "status":
            return decision.model_copy(
                update={
                    "worker": "conversation",
                    "intent": "status",
                    "dispatch": False,
                    "job_action": None,
                }
            )
        if is_approval_utterance(text):
            return decision.model_copy(
                update={
                    "worker": "conversation",
                    "intent": "conversation",
                    "dispatch": False,
                    "job_action": None,
                }
            )
        return decision

    explicit_action = detect_job_control_verb(text)
    if is_job_status_inquiry(text) and explicit_action is None:
        return decision.model_copy(
            update={
                "worker": "conversation",
                "intent": "status",
                "dispatch": False,
                "job_action": None,
                "target_id": None,
            }
        )

    if is_approval_utterance(text):
        return decision.model_copy(
            update={
                "worker": "conversation",
                "intent": "conversation",
                "dispatch": False,
                "job_action": None,
                "target_id": None,
            }
        )

    if explicit_action and decision.job_action != explicit_action:
        return decision.model_copy(update={"job_action": explicit_action})

    if explicit_action is None:
        return decision.model_copy(
            update={
                "worker": "conversation",
                "intent": "status",
                "dispatch": False,
                "job_action": None,
                "target_id": None,
            }
        )

    return decision
