from app.db import ToolContext
from app.tools import dock


def test_enqueue_and_list_order(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="d1", store=v2_store)
    a1 = dock.enqueue_pending_approval(
        ctx, approval_type="placement", title="A", payload={"x": 1}
    )
    a2 = dock.enqueue_pending_approval(
        ctx, approval_type="reorg", title="B", payload={"y": 2}
    )
    items = dock.list_pending_approvals(ctx)["items"]
    assert [i["id"] for i in items] == [a1, a2]


def test_suggested_actions_crowded(v2_store, v2_project):
    from app.models import NodeKind, V2Edge, V2Node, new_id

    ctx = ToolContext(project_id=v2_project.id, thread_id="d1", store=v2_store)
    hub = V2Node(
        _id=new_id("hub"),
        title="Crowded",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=v2_project.id,
    )
    v2_store.upsert_node(hub)
    for i in range(9):
        leaf = V2Node(
            _id=new_id("leaf"),
            title=f"L{i}",
            description="",
            node_kind=NodeKind.NOTE,
            project_id=v2_project.id,
        )
        v2_store.upsert_node(leaf)
        v2_store.add_edge(
            V2Edge(
                _id=new_id("e"),
                source_id=hub.id,
                target_id=leaf.id,
                project_id=v2_project.id,
            )
        )
    out = dock.get_suggested_next_actions(ctx)
    assert any(s["type"] == "reorg" for s in out["suggestions"])
