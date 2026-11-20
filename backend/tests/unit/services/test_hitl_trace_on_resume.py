from pathlib import Path

from app.agents.graph import resume_approval
from app.models import Node, NodeKind, PendingApproval, new_id
from app.tools import gist


def test_placement_approve_appends_hitl_trace(store, project, monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_DIR", str(tmp_path))
    monkeypatch.setattr("app.config.settings.DECISION_TRACE_ENABLED", True)

    from app.db import ToolContext

    ctx = ToolContext(project_id=project.id, thread_id="voice-global", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub_a = Node(
        _id=new_id("hub"),
        title="A",
        description="",
        node_kind=NodeKind.INSIGHT,
        project_id=project.id,
    )
    hub_b = Node(
        _id=new_id("hub"),
        title="B",
        description="",
        node_kind=NodeKind.INSIGHT,
        project_id=project.id,
    )
    store.upsert_node(hub_a)
    store.upsert_node(hub_b)

    item = PendingApproval(
        _id="ap1",
        project_id=project.id,
        thread_id="voice-global",
        approval_type="placement",
        title="Connect",
        payload={
            "root_id": root["root_id"],
            "candidates": [(hub_a.id, 0.6), (hub_b.id, 0.4)],
        },
        status="pending",
    )
    store.enqueue_approval(item)

    resume_approval(
        store=store,
        project_id=project.id,
        thread_id="voice-global",
        approval_id="ap1",
        action="approve",
    )

    files = list((tmp_path / project.id).glob("*.jsonl"))
    assert files
    text = files[0].read_text(encoding="utf-8")
    assert "placement_hitl" in text
    assert "label_relevance" in text
