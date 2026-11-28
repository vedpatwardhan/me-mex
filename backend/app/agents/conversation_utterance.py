"""Shared Conversation LLM utterance builder for voice and observer paths."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from enum import StrEnum
from typing import Any

from app.agents.source_reference import resolve_source_reference
from app.config import settings
from app.llm import get_chains
from app.llm.chains import is_chains_overridden
from app.prompts import load_prompt
from app.services.llm_gateway import llm_gateway

EMERGENCY_FALLBACK = "Something went wrong generating a reply. Check the dock for status."
SCOPE_APPROVAL_EMERGENCY = (
    "Thanks for approving the project scope. What source would you like to start with?"
)

_FORBIDDEN_DISPATCH_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"arxiv\.org", re.IGNORECASE),
    re.compile(r"\bdoi:", re.IGNORECASE),
)


def conversation_prompt_inputs(
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
            "voice_phase",
            "completed_worker_results",
            "active_jobs",
            "recent_jobs",
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
    if briefing.get("scope_complete") is False and not (project_scope or "").strip():
        augmented += (
            "\nProject scope is not committed yet. "
            "Include the words scope and sources in your reply and end with a question."
        )
    return {"text": augmented, "project_scope": scope}


def _conversation_openai_messages(inp: dict[str, Any]) -> list[dict[str, Any]]:
    system = load_prompt("conversation", project_scope=inp.get("project_scope") or "")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": inp["text"]},
    ]


def _p1_onboarding_turn(inp: dict[str, Any]) -> bool:
    blob = str(inp.get("text") or "")
    if "utterance_context" in blob:
        return False
    return '"scope_complete": false' in blob or '"scope_complete": false' in blob.replace(" ", "")


def _ensure_p1_question_suffix(reply: str) -> str:
    text = (reply or "").strip()
    if not text or "?" in text:
        return text
    return f"{text} What would you like to explore first?"


async def astream_voice_conversation_reply(inp: dict[str, Any]) -> AsyncIterator[str]:
    """Stream conversation tokens (plane 1 TTS source)."""
    if settings.CHAT_LLM_MODE != "live" or is_chains_overridden():
        chains = get_chains()
        reply = chains.conversation.invoke(inp)
        if not isinstance(reply, str):
            reply = str(reply)
        if _p1_onboarding_turn(inp):
            reply = _ensure_p1_question_suffix(reply)
        step = max(1, min(32, len(reply) // 4 or 1))
        for i in range(0, len(reply), step):
            yield reply[i : i + step]
        return

    messages = _conversation_openai_messages(inp)
    pieces: list[str] = []
    async for piece in llm_gateway.stream_chat_completion(
        messages,
        max_tokens=settings.VOICE_FOREGROUND_MAX_TOKENS,
        enable_reasoning=False,
        caller="Conversation",
    ):
        if not piece:
            continue
        pieces.append(piece)
        yield piece
    if _p1_onboarding_turn(inp):
        reply = "".join(pieces)
        if reply and "?" not in reply:
            suffix = " What would you like to explore first?"
            pieces.append(suffix)
            yield suffix


def _yield_chunks(text: str, width: int = 32) -> list[str]:
    return [text[i : i + width] for i in range(0, len(text), width)]


class UtteranceIntent(StrEnum):
    NORMAL_TURN = "normal_turn"
    DISPATCH_INTERIM = "dispatch_interim"
    MULTI_DISPATCH_INTERIM = "multi_dispatch_interim"
    CLARIFICATION = "clarification"
    JOB_CONTROL_RESULT = "job_control_result"
    PROACTIVE_COMPLETE = "proactive_complete"
    PROACTIVE_REVIEW = "proactive_review"
    GIST_FOLLOWUP = "gist_followup"
    APPROVAL_ACK = "approval_ack"


def strip_source_fields_for_intent(
    intent: UtteranceIntent,
    user_fields: dict[str, Any] | None,
) -> dict[str, Any]:
    """For dispatch/clarification intents, drop fields at conversation_voice layer too."""
    if intent in {
        UtteranceIntent.DISPATCH_INTERIM,
        UtteranceIntent.MULTI_DISPATCH_INTERIM,
        UtteranceIntent.CLARIFICATION,
    }:
        return {}
    return user_fields or {}


def build_conversation_turn(
    *,
    intent: UtteranceIntent,
    user_message: str,
    briefing: dict[str, Any],
    project_scope: str,
    user_fields: dict[str, Any] | None = None,
    utterance_facts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build Conversation chain input with utterance_intent metadata."""
    safe_fields = strip_source_fields_for_intent(intent, user_fields)
    facts = utterance_facts or {}
    base = conversation_prompt_inputs(
        text=user_message,
        briefing=briefing,
        project_scope=project_scope,
        user_fields=safe_fields,
    )
    meta = json.dumps(
        {"utterance_intent": intent.value, "utterance_facts": facts},
        ensure_ascii=False,
    )[:2000]
    base["text"] = f"[utterance_context]{meta}[/utterance_context]\n{base['text']}"
    return base


def _dispatch_violates_evidence_boundary(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return True
    return any(p.search(text) for p in _FORBIDDEN_DISPATCH_PATTERNS)


async def astream_conversation_utterance(
    inp: dict[str, Any],
    *,
    intent: UtteranceIntent,
) -> AsyncIterator[str]:
    """Stream a Conversation reply; apply dispatch evidence lint for interim intents."""
    dispatch_guard = intent in (
        UtteranceIntent.DISPATCH_INTERIM,
        UtteranceIntent.MULTI_DISPATCH_INTERIM,
    )
    if not dispatch_guard:
        async for piece in astream_voice_conversation_reply(inp):
            yield piece
        return

    pieces: list[str] = []
    async for piece in astream_voice_conversation_reply(inp):
        pieces.append(piece)
    text = "".join(pieces).strip()
    if _dispatch_violates_evidence_boundary(text):
        import logging

        logging.getLogger("memex.v2.voice").warning(
            "dispatch utterance failed evidence lint; retrying once"
        )
        retry_inp = dict(inp)
        retry_inp["text"] = (
            inp["text"] + "\n[reminder]Do not mention URLs, hosts, or paper content. "
            "Acknowledge the task and dock only.[/reminder]"
        )
        pieces = []
        async for piece in astream_voice_conversation_reply(retry_inp):
            pieces.append(piece)
        text = "".join(pieces).strip()
        if _dispatch_violates_evidence_boundary(text):
            text = EMERGENCY_FALLBACK
    for chunk in _yield_chunks(text):
        yield chunk


def invoke_conversation_utterance(
    inp: dict[str, Any],
    *,
    intent: UtteranceIntent,
    max_tokens: int | None = None,
) -> str:
    """Synchronous Conversation invoke for observer / graph approval paths."""
    if settings.CHAT_LLM_MODE != "live" or is_chains_overridden():
        chains = get_chains()
        reply = chains.conversation.invoke(inp)
        return str(reply or "").strip()

    messages = _conversation_openai_messages(inp)
    budget = max_tokens or settings.VOICE_FOREGROUND_MAX_TOKENS
    reply = llm_gateway.generate_chat_completion(
        messages,
        max_tokens=budget,
        enable_reasoning=False,
        caller="Conversation",
    )
    text = str(reply or "").strip()
    if intent in (
        UtteranceIntent.DISPATCH_INTERIM,
        UtteranceIntent.MULTI_DISPATCH_INTERIM,
    ) and _dispatch_violates_evidence_boundary(text):
        return EMERGENCY_FALLBACK
    return text or EMERGENCY_FALLBACK
