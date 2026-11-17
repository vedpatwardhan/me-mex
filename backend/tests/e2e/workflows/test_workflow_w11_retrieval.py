from app.v2.db import ToolContext
from app.v2.models import NodeKind, V2Edge, V2Node, new_id
from app.v2.tools import gist


def test_w11_retrieval_highlight(client, v2_store, v2_project_scoped):
    pid = v2_project_scoped.id
    seed = V2Node(
        _id=new_id("seed"),
        title="Manipulation",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    v2_store.upsert_node(seed)
    leaf = V2Node(
        _id=new_id("leaf"),
        title="Policy",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=pid,
    )
    v2_store.upsert_node(leaf)
    v2_store.add_edge(
        V2Edge(_id=new_id("e"), source_id=seed.id, target_id=leaf.id, project_id=pid)
    )
    r = client.post(
        "/api/v2/agent/turn",
        json={
            "text": "what relates to manipulation?",
            "thread_id": "w11",
            "context_json": {
                "active_project_id": pid,
                "custom_fields": {"query_node_id": seed.id},
            },
        },
    )
    assert r.json()["graph_write"] is False
    assert v2_store.get_highlight_ids("w11")
