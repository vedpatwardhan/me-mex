import pytest
from app.db import ToolContext
from app.models import Node, NodeKind, new_id
from app.tools import gist, link


def test_create_root_insight_edges(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub = Node(
        _id=new_id("hub"),
        title="Hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=project.id,
    )
    store.upsert_node(hub)
    out = link.create_root_insight_edges(ctx, root_id=root["root_id"], target_ids=[hub.id])
    assert len(out["edge_ids"]) == 1


def test_root_to_concept_i_forbidden(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="t1", store=store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    ci = Node(
        _id=new_id("ci"),
        title="C",
        description="",
        node_kind=NodeKind.CONCEPT_I,
        project_id=project.id,
    )
    store.upsert_node(ci)
    with pytest.raises(ValueError, match="CONCEPT_I"):
        link.create_root_insight_edges(ctx, root_id=root["root_id"], target_ids=[ci.id])


def test_highlight_and_keyword(store, project):
    ctx = ToolContext(project_id=project.id, thread_id="hl", store=store)
    gist.create_or_update_root_gist(ctx, title="Alpha paper", gist="g")
    link.highlight_nodes(ctx, node_ids=["n1", "n2"])
    assert store.get_highlight_ids("hl") == ["n1", "n2"]
    hits = link.search_nodes_keyword(ctx, query="alpha")
    assert hits["results"]
