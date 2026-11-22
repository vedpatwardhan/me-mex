"""P1 scope: incremental correction vs full replace."""

from dataclasses import replace
from uuid import uuid4

from app.agents import scope_proposal, session_plane
from app.api import routes
from app.llm import get_chains, set_chains_override
from app.llm.schemas import ProjectScopeResult, WorkerRoute
from app.models import PendingApproval
from app.services.checkpoints import JsonCheckpointStore
from langchain_core.runnables import RunnableLambda


def test_p1_scope_incremental_correction_keeps_baseline(
    client, empty_project, store, tmpdir_checkpoint, monkeypatch
):
    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(scope_proposal, "_checkpoint", checkpoint)
    monkeypatch.setattr(session_plane, "_checkpoint", checkpoint)
    monkeypatch.setattr(routes, "_checkpoints", checkpoint)

    baseline = (
        "Explore recursive self-improvement (RSI): autonomous model improvement via "
        "weights-based programming, distillation, and research papers."
    )
    thread_id = f"p1-incremental-{uuid4().hex}"
    store.enqueue_approval(
        PendingApproval(
            _id="appr_inc",
            project_id=empty_project.id,
            thread_id=thread_id,
            approval_type="project_scope",
            title="Review",
            payload={"proposed_introduction": baseline},
        )
    )
    scope_proposal.update_scope_proposal(thread_id, baseline)

    def reviser(inp):
        import json

        payload = json.loads(inp["payload"])
        assert "RSI" in payload["baseline_proposal"]
        assert payload["pending_scope_approval"] is True
        assert payload["force_scope_rewrite"] is False
        assert "revision_mode" not in payload
        return ProjectScopeResult(
            revision_mode="incremental",
            proposed_introduction=payload["baseline_proposal"].replace(
                "weights-based", "weight-based"
            ),
        )

    route = WorkerRoute(worker="project_scope", intent="scope_conversation", dispatch=True)
    set_chains_override(
        replace(
            get_chains(),
            supervisor=RunnableLambda(lambda _inputs: route),
            project_scope=RunnableLambda(reviser),
        )
    )
    response = client.post(
        "/api/agent/turn",
        json={
            "text": "Small fix: say weight-based programming, not weights-based.",
            "thread_id": thread_id,
            "context_json": {"active_project_id": empty_project.id},
        },
    )
    assert response.status_code == 200
    assert response.json()["details"]["scope_revision_mode"] == "incremental"
    approvals = client.get(
        "/api/agent/approvals",
        params={"project_id": empty_project.id, "thread_id": thread_id},
    ).json()["items"]
    proposal = approvals[-1]["payload"]["proposed_introduction"]
    assert "weight-based" in proposal
    assert "RSI" in proposal or "recursive" in proposal.lower()
    assert len(approvals) == 1


def test_p1_scope_full_replace(client, empty_project, store, tmpdir_checkpoint, monkeypatch):
    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(scope_proposal, "_checkpoint", checkpoint)
    monkeypatch.setattr(session_plane, "_checkpoint", checkpoint)
    monkeypatch.setattr(routes, "_checkpoints", checkpoint)

    baseline = "Robotics manipulation for warehouse picking."
    thread_id = f"p1-replace-{uuid4().hex}"
    scope_proposal.update_scope_proposal(thread_id, baseline)

    def replacer(inp):
        import json

        payload = json.loads(inp["payload"])
        assert "Robotics manipulation" in payload["baseline_proposal"]
        return ProjectScopeResult(
            revision_mode="replace",
            proposed_introduction="Computational biology: protein folding literature review.",
        )

    set_chains_override(
        replace(
            get_chains(),
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="project_scope",
                    intent="scope_conversation",
                    dispatch=True,
                )
            ),
            project_scope=RunnableLambda(replacer),
        )
    )
    response = client.post(
        "/api/agent/turn",
        json={
            "text": "Start over — this project is computational biology, not robotics.",
            "thread_id": thread_id,
            "context_json": {"active_project_id": empty_project.id},
        },
    )
    assert response.status_code == 200
    assert response.json()["worker"] == "project_scope"
    approvals = client.get(
        "/api/agent/approvals",
        params={"project_id": empty_project.id, "thread_id": thread_id},
    ).json()["items"]
    assert "biology" in approvals[-1]["payload"]["proposed_introduction"].lower()
    assert "robotics" not in approvals[-1]["payload"]["proposed_introduction"].lower()
