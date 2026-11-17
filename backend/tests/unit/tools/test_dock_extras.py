from app.db import ToolContext
from app.models import Node, NodeKind, new_id
from app.tools import dock


def test_open_passages_truncates(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t", store=store)
    store._db.passages.insert_one(
        {"_id": "p1", "text_content": "x" * 20000, "project_id": project.id}
    )
    out = dock.open_passages(ctx, passage_ids=["p1"], max_chars=100)
    assert len(out["text"]) <= 100


def test_get_suggested_crowded_hub(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t", store=store)
    hub = Node(
        _id=new_id("hub"),
        title="Crowded",
        node_kind=NodeKind.CONCEPT_M,
        project_id=project.id,
    )
    store.upsert_node(hub)
    from app.models import Edge

    for _ in range(8):
        leaf = Node(
            _id=new_id("l"),
            title="L",
            node_kind=NodeKind.CONCEPT_M,
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
    nudges = dock.get_suggested_next_actions(ctx)
    assert any(n["node_id"] == hub.id for n in nudges["suggestions"])
