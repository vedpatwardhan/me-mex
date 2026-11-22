from app.agents import scope_proposal
from app.agents.scope_proposal import build_project_scope_llm_payload, normalize_scope_result
from app.db import ToolContext
from app.llm.schemas import ProjectScopeResult
from app.models import PendingApproval
from app.services.checkpoints import JsonCheckpointStore


def test_scope_payload_uses_active_pending_proposal_before_committed_scope(
    store, project, tmpdir_checkpoint, monkeypatch
):
    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(scope_proposal, "_checkpoint", checkpoint)
    committed = "Robotics manipulation for warehouse picking."
    pending = "RSI research focused on weight-space programming."
    store.update_project_scope(project.id, committed)
    thread_id = "scope-active-baseline"
    store.enqueue_approval(
        PendingApproval(
            _id="appr_active_scope",
            project_id=project.id,
            thread_id=thread_id,
            approval_type="project_scope",
            title="Review",
            payload={"proposed_introduction": pending},
        )
    )

    ctx = ToolContext(project_id=project.id, thread_id=thread_id, store=store)
    payload = build_project_scope_llm_payload(
        ctx,
        "Correction: say weight-space programming.",
        context={},
    )

    assert payload["baseline_proposal"] == pending
    assert payload["committed_scope"] == committed
    assert payload["pending_scope_approval"] is True
    assert "revision_mode" not in payload


def test_scope_payload_passes_explicit_force_rewrite_flag(
    store, project, tmpdir_checkpoint, monkeypatch
):
    checkpoint = JsonCheckpointStore(str(tmpdir_checkpoint))
    monkeypatch.setattr(scope_proposal, "_checkpoint", checkpoint)
    store.update_project_scope(project.id, "Existing project scope.")
    ctx = ToolContext(project_id=project.id, thread_id="scope-force-rewrite", store=store)

    payload = build_project_scope_llm_payload(
        ctx,
        "Move to another research area.",
        context={"custom_fields": {"force_scope_rewrite": "true"}},
    )

    assert payload["baseline_proposal"] == "Existing project scope."
    assert payload["force_scope_rewrite"] is True


def test_project_scope_result_mode_fallbacks_and_force_override():
    result = ProjectScopeResult(
        revision_mode="incremental",
        proposed_introduction="Updated scope while preserving the baseline.",
    )
    assert normalize_scope_result(result, {"baseline_proposal": "Current scope"}).revision_mode == (
        "incremental"
    )
    assert normalize_scope_result(result, {"baseline_proposal": ""}).revision_mode == "replace"
    assert (
        normalize_scope_result(
            result,
            {"baseline_proposal": "Current scope", "force_scope_rewrite": True},
        ).revision_mode
        == "replace"
    )
