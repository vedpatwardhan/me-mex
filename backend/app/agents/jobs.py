"""Session job ledger (04 §12.4)."""

from __future__ import annotations

from typing import Any, TypedDict


class JobRecord(TypedDict, total=False):
    job_id: str
    kind: str
    label: str
    status: str
    worker: str
    recommendation_id: str
    progress: str


def new_job_id() -> str:
    from app.models import new_id

    return new_id("job")


def upsert_job(jobs: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    jid = record.get("job_id")
    if not jid:
        record = {**record, "job_id": new_job_id()}
        jid = record["job_id"]
    out = [j for j in jobs if j.get("job_id") != jid]
    out.append(record)
    return out


def job_from_worker_turn(worker: str, text: str, output: dict[str, Any]) -> dict[str, Any]:
    status = "awaiting_approval" if output.get("approval_id") else "done"
    if output.get("graph_write"):
        status = "awaiting_approval" if output.get("approval_id") else "done"
    return {
        "job_id": new_job_id(),
        "kind": worker,
        "label": (text or "")[:80],
        "status": status,
        "worker": worker,
        "recommendation_id": output.get("approval_id"),
        "progress": output.get("progress", ""),
    }
