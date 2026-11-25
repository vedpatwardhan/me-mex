"""Keyword-based routing when CHAT_LLM_MODE=stub (offline only — not used when .env.test is live)."""

from __future__ import annotations

from app.config import settings
from app.llm.schemas import WorkerRoute
from app.models import Project


def keyword_route(text: str, context: dict, project: Project) -> WorkerRoute:
    """Deterministic fallback; the live Supervisor path must never call this."""
    if settings.CHAT_LLM_MODE == "live":
        raise RuntimeError("keyword_route is only available when CHAT_LLM_MODE=stub")

    # This deliberately lightweight classifier exists only to keep no-LLM tests
    # deterministic. Production semantic routing is the structured Supervisor.
    t = text.lower()
    fields = context.get("custom_fields") or {}
    from app.agents.source_reference import resolve_source_reference

    source = resolve_source_reference(text, fields)
    source_field = source.field_name or ("raw_text" if fields.get("raw_text") else None)
    if any(
        phrase in t
        for phrase in ("deep read", "intra-doc", "staging", "detailed", "in detail", "analysis")
    ):
        return WorkerRoute(
            worker="intradoc",
            intent="source_analysis",
            dispatch=True,
            source_field=source_field,
            source_reference=source.url,
        )
    if source.url and any(
        phrase in t
        for phrase in (
            "gist",
            "summary",
            "summarize",
            "summarise",
            "overview",
            "what is this paper about",
        )
    ):
        return WorkerRoute(
            worker="gist",
            intent="source_summary",
            dispatch=True,
            source_field=source.field_name,
            source_reference=source.url,
        )
    if any(phrase in t for phrase in ("create root", "save gist", "commit gist")) or fields.get(
        "force_gist_commit"
    ):
        return WorkerRoute(
            worker="gist",
            intent="commit_gist",
            dispatch=True,
            source_field=source_field,
            source_reference=source.url,
            title=fields.get("title"),
            content=fields.get("gist"),
        )
    if "create note" in t or "add note" in t:
        return WorkerRoute(
            worker="scratch",
            intent="create_note",
            dispatch=True,
            title=fields.get("title")
            or (text.split(":", 1)[-1].strip() if ":" in text else "Note"),
            content=fields.get("body"),
        )
    if "create todo" in t or "add todo" in t:
        return WorkerRoute(
            worker="scratch",
            intent="create_todo",
            dispatch=True,
            title=fields.get("title")
            or (text.split(":", 1)[-1].strip() if ":" in text else "ToDo"),
            content=fields.get("body"),
        )
    if "promote todo" in t or fields.get("promote_todo_id"):
        return WorkerRoute(
            worker="scratch",
            intent="promote_todo",
            dispatch=True,
            target_id=fields.get("promote_todo_id"),
        )
    if "where does" in t or "connect" in t or "place" in t:
        return WorkerRoute(worker="link", intent="link", dispatch=True)
    if "reorg" in t or "split" in t:
        return WorkerRoute(worker="reorg", intent="reorg", dispatch=True)
    if "what relates" in t or "retrieval" in t or "highlight" in t:
        return WorkerRoute(worker="retrieval", intent="retrieval", dispatch=True)
    if any(phrase in t for phrase in ("pause", "resume", "abort", "delete job", "remove job")):
        jobs = (context.get("session_state") or {}).get("active_jobs") or []
        job_id = str(jobs[0]["job_id"]) if len(jobs) == 1 else None
        if "pause" in t or "hold" in t or "suspend" in t:
            action = "pause"
        elif "resume" in t or "unpause" in t:
            action = "resume"
        elif "delete" in t or "remove" in t:
            action = "delete"
        else:
            action = "cancel"
        return WorkerRoute(
            worker="job_control",
            intent="job_control",
            dispatch=True,
            target_id=job_id,
            job_action=action,
        )
    if "cancel" in t and "status" not in t:
        jobs = (context.get("session_state") or {}).get("active_jobs") or []
        job_id = str(jobs[0]["job_id"]) if len(jobs) == 1 else None
        return WorkerRoute(
            worker="job_control",
            intent="job_control",
            dispatch=True,
            target_id=job_id,
            job_action="cancel",
        )
    if any(word in t for word in ("status", "progress", "status check", "still running")):
        return WorkerRoute(worker="conversation", intent="status", dispatch=False)
    if "approve" in t or "dismiss" in t:
        return WorkerRoute(worker="conversation", intent="conversation", dispatch=False)
    if "save scope" in t or "update_project_scope" in t:
        return WorkerRoute(
            worker="project_scope",
            intent="scope_save",
            dispatch=True,
            content=text.split(":", 1)[-1].strip() if ":" in text else None,
        )
    if not (project.introduction or "").strip() and (
        "scope" in t or "introduction" in t or t.strip() in ("hello", "hi")
    ):
        return WorkerRoute(worker="project_scope", intent="scope_conversation", dispatch=False)
    if not (project.introduction or "").strip() and len(text.strip()) >= 30:
        return WorkerRoute(worker="project_scope", intent="scope_conversation", dispatch=True)
    return WorkerRoute(worker="conversation", intent="conversation", dispatch=False)
