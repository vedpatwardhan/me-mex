import pytest

from app.db import ToolContext
from app.models import NodeKind, V2Edge, V2Node, new_id
from app.tools import gist, link


def test_create_root_insight_edges(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="t1", store=v2_store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    hub = V2Node(
        _id=new_id("hub"),
        title="Hub",
        description="",
        node_kind=NodeKind.CONCEPT_M,
        project_id=v2_project.id,
    )
    v2_store.upsert_node(hub)
    out = link.create_root_insight_edges(
        ctx, root_id=root["root_id"], target_ids=[hub.id]
    )
    assert len(out["edge_ids"]) == 1


def test_root_to_concept_i_forbidden(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="t1", store=v2_store)
    root = gist.create_or_update_root_gist(ctx, title="R", gist="g")
    ci = V2Node(
        _id=new_id("ci"),
        title="C",
        description="",
        node_kind=NodeKind.CONCEPT_I,
        project_id=v2_project.id,
    )
    v2_store.upsert_node(ci)
    with pytest.raises(ValueError, match="CONCEPT_I"):
        link.create_root_insight_edges(ctx, root_id=root["root_id"], target_ids=[ci.id])


def test_highlight_and_keyword(v2_store, v2_project):
    ctx = ToolContext(project_id=v2_project.id, thread_id="hl", store=v2_store)
    gist.create_or_update_root_gist(ctx, title="Alpha paper", gist="g")
    link.highlight_nodes(ctx, node_ids=["n1", "n2"])
    assert v2_store.get_highlight_ids("hl") == ["n1", "n2"]
    hits = link.search_nodes_keyword(ctx, query="alpha")
    assert hits["results"]
