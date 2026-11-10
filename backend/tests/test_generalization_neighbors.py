"""Generalization neighbor batch matches partition (excludes tree parent)."""

import pytest

from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.agents.graph_navigator import GraphNavigator
from app.services.graph_analytics import MutableTreeIndex
from app.services.graph_link_utils import MUTABLE_PARENT_META_KEY, set_mutable_parent


@pytest.fixture
def project_id():
    return "test_generalization_neighbors"


def test_generalization_neighbor_batch_excludes_parent(project_id):
    parent = GraphNode(
        _id="gen_parent",
        node_type="CONCEPT",
        title="Parent Hub",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="gen_hub",
        node_type="CONCEPT",
        title="Child Hub",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "gen_parent"},
    )
    imm = GraphNode(
        _id="gen_imm",
        node_type="CONCEPT",
        title="Evidence Leaf",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for n in (parent, hub, imm):
        db_engine.upsert_node(n)
    set_mutable_parent("gen_hub", "gen_parent", [project_id], project_id)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_gen_imm",
            source_id="gen_imm",
            target_id="gen_hub",
            description="linked",
            project_ids=[project_id],
        )
    )

    tree = MutableTreeIndex(project_id=project_id)
    entries = GraphNavigator._neighbor_entries_for_hub("gen_hub", project_id, tree)
    ids = {e["id"] for e in entries}
    assert "gen_parent" not in ids
    assert "gen_imm" in ids
