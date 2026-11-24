"""Session briefing types (04 §12.11)."""

from __future__ import annotations

from typing import TypedDict


class ActiveJobBrief(TypedDict, total=False):
    job_id: str
    kind: str
    status: str
    label: str
    worker: str


class RecommendationCard(TypedDict, total=False):
    id: str
    title: str
    rank: int
    className: str


class SessionBriefing(TypedDict, total=False):
    project_scope_snippet: str
    scope_complete: bool
    voice_phase: str
    active_jobs: list[ActiveJobBrief]
    recent_jobs: list[dict[str, str]]
    active_job_affinity: list[str]
    last_route: str
    pending_approval_count: int
    completed_worker_results: list[dict[str, str]]
    scope_proposal_preview: str
    worker_result_snippet: str
    recommendation_cards: list[RecommendationCard]
    proactive_script: str
