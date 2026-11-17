from app.db import ToolContext
from app.tools import dock


def test_enqueue_and_list_order(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="d1", store=store)
    a1 = dock.enqueue_pending_approval(
        ctx, approval_type="placement", title="A", payload={"x": 1}
    )
    a2 = dock.enqueue_pending_approval(
        ctx, approval_type="reorg", title="B", payload={"y": 2}
    )
    items = dock.list_pending_approvals(ctx)["items"]
    assert [i["id"] for i in items] == [a1, a2]


def test_suggested_actions_crowded(store, project):
    from app.models import NodeKind, Edge, Node, new_id

    ctx = ToolContext(project_id=project.id, thread_id="d1", store=store)
    hub = Node(
        _id=new_id("hub"),
        title="Crowded",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=project.id,
    )
    store.upsert_node(hub)
    for i in range(9):
        leaf = Node(
            _id=new_id("leaf"),
            title=f"L{i}",
            description="",
            node_kind=NodeKind.NOTE,
            project_id=project.id,
        )
        store.upsert_node(leaf)
        store.add_edge(
            Edge(
                _id=new_id("e"),
                source_id=hub.id,
                target_id=leaf.id,
                project_id=project.id,
            )
        )
    out = dock.get_suggested_next_actions(ctx)
    assert any(s["type"] == "reorg" for s in out["suggestions"])
