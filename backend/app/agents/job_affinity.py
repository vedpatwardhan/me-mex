"""Resolve whether a worker dispatch creates or updates an open job (04 §12.4)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

from app.agents.context_preprocessor import project_scope_complete
from app.agents.source_reference import resolve_source_reference

_OPEN_STATUSES = frozenset({"running", "paused", "awaiting_approval"})


@dataclass
class JobDispatchPlan:
    action: Literal["create", "update", "skip"]
    job_id: str | None = None
    approval_id: str | None = None
    affinity_key: str = ""
    reason: str = ""


def affinity_key_for_worker(
    worker_kind: str,
    *,
    project_id: str,
    context_json: dict[str, Any],
    introduction: str = "",
) -> str:
    fields = context_json.get("custom_fields") or {}
    if worker_kind == "project_scope":
        return f"scope:{project_id}"
    if worker_kind == "intradoc":
        root = fields.get("root_id") or ""
        decision = context_json.get("supervisor_decision") or {}
        source = (
            resolve_source_reference(
                "",
                fields,
                selected_reference=decision.get("source_reference"),
                selected_field=decision.get("source_field"),
            ).url
            or ""
        )
        token = root or source or fields.get("staging_key") or project_id
        if source and not root:
            token = hashlib.sha256(source.encode()).hexdigest()[:12]
        return f"intradoc:{token}"
    if worker_kind == "gist":
        root = fields.get("root_id") or ""
        decision = context_json.get("supervisor_decision") or {}
        source = (
            resolve_source_reference(
                "",
                fields,
                selected_reference=decision.get("source_reference"),
                selected_field=decision.get("source_field"),
            ).url
            or ""
        )
        token = root or source or project_id
        if source and not root:
            token = hashlib.sha256(source.encode()).hexdigest()[:12]
        return f"gist:{token}"
    if worker_kind == "link":
        decision = context_json.get("supervisor_decision") or {}
        root = fields.get("root_id") or decision.get("root_id") or project_id
        targets = fields.get("target_ids") or decision.get("target_ids") or []
        if isinstance(targets, str):
            targets = [targets]
        if not targets and decision.get("target_id"):
            targets = [decision["target_id"]]
        target_token = ",".join(sorted(str(target) for target in targets))
        return f"link:{root}:{target_token}"
    if worker_kind in ("reorg", "retrieval"):
        root = fields.get("root_id") or project_id
        return f"{worker_kind}:{root}"
    return f"{worker_kind}:{project_id}"


def _open_job_for_affinity(jobs: list[dict[str, Any]], affinity_key: str) -> dict[str, Any] | None:
    for job in reversed(jobs):
        if job.get("affinity_key") != affinity_key:
            continue
        if job.get("status") in _OPEN_STATUSES:
            return job
    return None


def _approval_for_type(
    pending: list,
    approval_type: str,
    affinity_key: str,
    project_id: str,
) -> Any | None:
    for item in pending:
        payload = item.payload or {}
        expected_affinity = payload.get("affinity_key")
        if not expected_affinity and approval_type == "project_scope":
            expected_affinity = f"scope:{project_id}"
        if (
            item.approval_type == approval_type
            and item.status == "pending"
            and expected_affinity == affinity_key
        ):
            return item
    return None


def resolve_job_dispatch(
    *,
    thread_id: str,
    project_id: str,
    worker_kind: str,
    effective_text: str,
    context_json: dict[str, Any],
    jobs: list[dict[str, Any]],
    pending_approvals: list,
    introduction: str = "",
    dispatch_allowed: bool = True,
) -> JobDispatchPlan:
    if not dispatch_allowed or worker_kind in ("conversation", "scratch", "job_control"):
        return JobDispatchPlan(action="skip", reason="dialogue_only")

    affinity_key = affinity_key_for_worker(
        worker_kind,
        project_id=project_id,
        context_json=context_json,
        introduction=introduction,
    )

    open_job = _open_job_for_affinity(jobs, affinity_key)
    if open_job:
        if open_job.get("status") in {"running", "paused"} and worker_kind != "project_scope":
            return JobDispatchPlan(
                action="skip",
                job_id=open_job.get("job_id"),
                approval_id=open_job.get("recommendation_id") or open_job.get("approval_id"),
                affinity_key=affinity_key,
                reason="already_running",
            )
        if open_job.get("status") == "awaiting_approval" and worker_kind != "project_scope":
            return JobDispatchPlan(
                action="skip",
                job_id=open_job.get("job_id"),
                approval_id=open_job.get("recommendation_id") or open_job.get("approval_id"),
                affinity_key=affinity_key,
                reason="pending_approval_match",
            )
        return JobDispatchPlan(
            action="update",
            job_id=open_job.get("job_id"),
            approval_id=open_job.get("recommendation_id") or open_job.get("approval_id"),
            affinity_key=affinity_key,
            reason="open_job_match",
        )

    approval_type_map = {
        "project_scope": "project_scope",
        "intradoc": "intra_doc_staging",
        "link": "placement",
        "reorg": "reorg",
        "gist": "gist_root",
    }
    atype = approval_type_map.get(worker_kind)
    if atype:
        pending = _approval_for_type(pending_approvals, atype, affinity_key, project_id)
        if pending:
            linked = _open_job_for_affinity(jobs, affinity_key)
            return JobDispatchPlan(
                action="update",
                job_id=linked.get("job_id") if linked else None,
                approval_id=pending.id,
                affinity_key=affinity_key,
                reason="pending_approval_match",
            )

    if worker_kind == "project_scope" and not project_scope_complete(introduction):
        return JobDispatchPlan(
            action="create",
            affinity_key=affinity_key,
            reason="new_scope_onboarding",
        )

    return JobDispatchPlan(
        action="create",
        affinity_key=affinity_key,
        reason="new_task",
    )
