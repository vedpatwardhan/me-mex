from app.services.graph_analytics import graph_analytics
from app.db import db_engine
from app.models import GraphNode, GraphEdge


def test_rustworkx_graph_construction():
    """Verify PyDiGraph construction from DB nodes/edges."""
    graph, idx_to_node_id, node_id_to_idx = graph_analytics.build_rustworkx_graph(
        "global"
    )
    assert len(graph) == 4
    assert "concept_action_mpc" in node_id_to_idx


def test_hub_centrality_calculation():
    """Verify eigenvector/degree centrality score ranking."""
    centrality = graph_analytics.calculate_hub_centrality("global")
    assert "concept_action_mpc" in centrality
    assert centrality["concept_action_mpc"] > 0.0


def test_project_scoped_concept_hubs():
    """Verify top concept hub discovery filters by project_id."""
    # Create project node and edge
    p_node = GraphNode(
        _id="concept_custom_p",
        title="Custom Project Hub",
        text_body="# Custom Hub\nUnique to proj_custom.",
        project_ids=["global", "proj_custom"],
    )
    db_engine.upsert_node(p_node)

    # Fetch hubs for proj_custom vs unrelated project
    custom_hubs = graph_analytics.get_top_concept_hubs(
        project_id="proj_custom", top_k=5
    )
    unrelated_hubs = graph_analytics.get_top_concept_hubs(
        project_id="proj_unrelated", top_k=5
    )

    assert any(node.id == "concept_custom_p" for node, score in custom_hubs)
    assert not any(node.id == "concept_custom_p" for node, score in unrelated_hubs)
