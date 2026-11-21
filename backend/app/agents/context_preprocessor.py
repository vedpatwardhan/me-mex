"""Deterministic turn prep helpers (custom_fields, P1 scope gate)—used by supervisor graph node and voice dispatch."""

from __future__ import annotations

from typing import Any


def apply_custom_fields_to_text(text: str, context_json: dict[str, Any] | None) -> str:
    """Append authoritative custom field values when present (02 §3)."""
    if not context_json:
        return text
    fields = context_json.get("custom_fields") or {}
    if not isinstance(fields, dict) or not fields:
        return text
    parts = [text.strip()] if text and text.strip() else []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        parts.append(f"{key}={value}")
    return "\n".join(parts)


def project_scope_complete(introduction: str | None) -> bool:
    return bool((introduction or "").strip())


def block_graph_writes_without_scope(introduction: str | None, worker: str) -> bool:
    """True when write workers must be blocked until P1 scope saved (04 §7)."""
    write_workers = {"gist", "intradoc", "link", "reorg"}
    if worker not in write_workers:
        return False
    return not project_scope_complete(introduction)


_DIALOGUE_WORKERS = frozenset({"conversation", "scratch"})


def prioritize_project_scope_until_complete(
    introduction: str | None,
    worker: str,
    context_json: dict[str, Any] | None,
) -> str:
    """Force P1 scope gate for graph writes; keep supervisor dialogue routes (04 §7, 06 P1)."""
    if project_scope_complete(introduction):
        return worker
    fields = (context_json or {}).get("custom_fields") or {}
    if fields.get("resume_job_id"):
        return worker
    if fields.get("force_project_scope"):
        return "project_scope"
    if worker in _DIALOGUE_WORKERS:
        return worker
    if block_graph_writes_without_scope(introduction, worker):
        return "project_scope"
    return worker
