"""Per-project rolling conversation summary for ingestion context."""

from __future__ import annotations

import time
from typing import List, Dict, Optional

from app.config import settings
from app.db import db_engine
from app.models import ProjectWorkspace
from app.services.llm_gateway import llm_gateway


def get_rolling_summary(project_id: str) -> str:
    project = db_engine.get_project(project_id)
    if not project or not getattr(project, "conversation_summary", None):
        return ""
    return project.conversation_summary or ""


def save_rolling_summary(project_id: str, summary: str) -> None:
    summary = summary.strip()[: settings.CHAT_SUMMARY_MAX_CHARS]
    project = db_engine.get_project(project_id)
    if not project:
        project = ProjectWorkspace(
            _id=project_id,
            name=project_id,
            description="",
        )
    project.conversation_summary = summary
    project.conversation_summary_updated_at = time.time()
    db_engine.upsert_project(project)


def _format_turns(chat_history: List[Dict[str, str]], max_turns: int) -> str:
    lines = []
    for item in chat_history[-max_turns:]:
        role = item.get("role", "user")
        content = (item.get("content") or item.get("text", ""))[:512]
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def refresh_rolling_summary_sync(
    project_id: str,
    chat_history: List[Dict[str, str]],
    *,
    latest_user_query: str = "",
    latest_assistant_reply: str = "",
) -> str:
    """Update stored summary from recent turns (synchronous LLM)."""
    if not settings.INGEST_USE_ROLLING_SUMMARY:
        return get_rolling_summary(project_id)

    prior = get_rolling_summary(project_id)
    new_turns = _format_turns(chat_history, settings.CHAT_SUMMARY_REFRESH_MIN_TURNS)
    if latest_user_query:
        new_turns += f"\nUSER: {latest_user_query[:512]}"
    if latest_assistant_reply:
        new_turns += f"\nASSISTANT: {latest_assistant_reply[:512]}"

    system = (
        "You maintain a concise rolling summary for a knowledge-graph assistant. "
        "Merge prior summary with new turns; keep facts about user goals, documents, "
        "and retrieval/ingestion intent. Max ~400 words. Plain text only."
    )
    user = (
        f"Prior summary:\n{prior or '(empty)'}\n\nNew turns:\n{new_turns or '(none)'}"
    )
    try:
        text = llm_gateway.generate_chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=1024,
            enable_reasoning=False,
            caller="ConversationSummary.refresh",
        )
        save_rolling_summary(project_id, text)
        return text
    except Exception:
        return prior


async def schedule_rolling_summary_refresh(
    project_id: str,
    chat_history: List[Dict[str, str]],
    *,
    latest_user_query: str = "",
    latest_assistant_reply: str = "",
) -> None:
    """Fire-and-forget summary refresh (does not block ingest)."""
    if not settings.INGEST_USE_ROLLING_SUMMARY:
        return
    import asyncio

    asyncio.create_task(
        asyncio.to_thread(
            refresh_rolling_summary_sync,
            project_id,
            chat_history,
            latest_user_query=latest_user_query,
            latest_assistant_reply=latest_assistant_reply,
        )
    )
