"""WorkflowAgent — dock card titles / proactive script (04 §12.4b)."""

from __future__ import annotations

from typing import Any

from app.agents.briefing import RecommendationCard


def run_workflow_agent(
    *,
    job: dict[str, Any],
    worker_output: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic stub; may call Ministral when CHAT_LLM_MODE=live."""
    status = job.get("status", "done")
    worker = job.get("worker") or job.get("kind") or "task"
    label = (job.get("label") or "")[:80]
    approval_id = worker_output.get("approval_id")

    title = f"{worker}: {label or status}".strip()
    cards: list[RecommendationCard] = []
    if approval_id:
        cards.append(
            {
                "id": approval_id,
                "title": title,
                "rank": 0,
                "className": "approval",
            }
        )
    elif status in ("done", "awaiting_approval"):
        cards.append(
            {
                "id": job.get("job_id", "job"),
                "title": title,
                "rank": 0,
                "className": "job",
            }
        )

    proactive_meta: dict[str, Any] | None = None
    if status == "awaiting_approval" and approval_id:
        proactive_meta = {
            "kind": "review",
            "worker": worker,
            "label": label,
            "approval_id": str(approval_id),
        }
    elif status == "done" and worker != "project_scope":
        proactive_meta = {
            "kind": "complete",
            "worker": worker,
            "label": label,
        }

    return {
        "recommendation_cards": cards,
        "proactive_meta": proactive_meta,
        "proactive_script": "",
    }
