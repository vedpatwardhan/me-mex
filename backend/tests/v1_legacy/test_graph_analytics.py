import pytest
from app.services.graph_analytics import graph_analytics, MutableTreeIndex
from app.db import db_engine
from app.models import GraphNode, GraphEdge

pytestmark = pytest.mark.xdist_group(name="worker1")


def test_rustworkx_graph_construction():
    graph, idx_to_node_id, node_id_to_idx = graph_analytics.build_rustworkx_graph(
        "global"
    )
    assert len(graph) >= 5
    assert "concept_genesis" in node_id_to_idx


def test_mutable_tree_index_parent_child():
    tree = graph_analytics.build_tree_index("global")
    assert tree.genesis_id == "concept_genesis"
    children = tree.mutable_children("concept_genesis")
    child_ids = {c.id for c in children}
    assert "concept_world_models" in child_ids


def test_mutable_tree_health_metrics():
    tree = graph_analytics.build_tree_index("global")
    metrics = tree.health_metrics(k=3)
    assert "sackin_index" in metrics
    assert "max_mutable_depth" in metrics
    assert metrics["immutable_reachable_pct_within_k"] >= 0.0


def test_refresh_tree_metadata_persists():
    graph_analytics.refresh_tree_metadata("global")
    node = db_engine.get_node("concept_world_models")
    assert node.metadata.get("tree_depth_from_genesis") is not None


def test_lateral_split_parent_resolution():
    proj = "proj_tree_lateral"
    genesis = GraphNode(
        _id="gen_lat",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[proj],
        metadata={"immutable": False, "is_genesis": True},
    )
    parent = GraphNode(
        _id="hub_parent",
        node_type="CONCEPT",
        title="Parent Hub",
        project_ids=[proj],
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="hub_overflow",
        node_type="CONCEPT",
        title="Overflow Hub",
        project_ids=[proj],
        metadata={"immutable": False},
    )
    for n in [genesis, parent, hub]:
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_p_g",
            source_id="hub_parent",
            target_id="gen_lat",
            description="SUBSET_OF",
            project_ids=[proj],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_h_p",
            source_id="hub_overflow",
            target_id="hub_parent",
            description="SUBSET_OF",
            project_ids=[proj],
        )
    )
    tree = MutableTreeIndex(project_id=proj)
    assert tree.parent_of("hub_overflow") == "hub_parent"
