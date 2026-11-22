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

    if status == "awaiting_approval" and approval_id:
        if worker == "project_scope":
            proactive = "There's a scope update to review in the dock."
        else:
            proactive = f"Your {worker} task is ready for review in the dock."
    elif status == "done" and worker != "project_scope":
        proactive = f"Finished {label or worker}." if label else f"{worker} is done."
    else:
        proactive = ""

    return {
        "recommendation_cards": cards,
        "proactive_script": proactive[:512],
    }
