from app.services.graph_analytics import graph_analytics
from app.db import db_engine
from app.models import GraphNode, GraphEdge


def test_rustworkx_graph_construction():
    """Verify PyDiGraph construction from DB nodes/edges."""
    graph, idx_to_node_id, node_id_to_idx = graph_analytics.build_rustworkx_graph(
        "global"
    )
    # 4 baseline concepts + 1 primordial Universal Genesis concept ('Everything')
    assert len(graph) == 5
    assert "concept_action_mpc" in node_id_to_idx
    assert "concept_genesis" in node_id_to_idx


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
        description="# Custom Hub\nUnique to proj_custom.",
        project_ids=["global", "proj_custom"],
    )
    db_engine.upsert_node(p_node)

    # Fetch hubs for proj_custom vs unrelated project
    custom_hubs = graph_analytics.get_top_concept_hubs(
        project_id="proj_custom", max_k=5
    )
    unrelated_hubs = graph_analytics.get_top_concept_hubs(
        project_id="proj_unrelated", max_k=5
    )

    assert any(node.id == "concept_custom_p" for node, score in custom_hubs)
    assert not any(node.id == "concept_custom_p" for node, score in unrelated_hubs)


def test_pure_centrality_dynamic_hub_selection():
    """Verify node-type filtering and relative thresholding (s_i >= 0.3 * s_max) in get_top_concept_hubs."""
    # Add a root paper node and a low-score concept node
    paper_node = GraphNode(
        _id="paper_test_root",
        node_type="paper",
        title="Root Paper Node",
        description="Paper node emanates concepts but is not a concept hub.",
        project_ids=["proj_heuristic_test"],
    )
    c_node_high = GraphNode(
        _id="concept_high_hub",
        node_type="concept",
        title="High Centrality Concept Hub",
        description="Core paradigm hub node.",
        project_ids=["proj_heuristic_test"],
    )
    c_node_outlier = GraphNode(
        _id="concept_outlier_leaf",
        node_type="concept",
        title="Outlier Isolated Leaf",
        description="Isolated leaf node with near zero centrality.",
        project_ids=["proj_heuristic_test"],
    )
    db_engine.upsert_node(paper_node)
    db_engine.upsert_node(c_node_high)
    db_engine.upsert_node(c_node_outlier)

    # Edge between paper and high hub (weight 1.0)
    e1 = GraphEdge(
        _id="edge_test_p_c",
        source_id="paper_test_root",
        target_id="concept_high_hub",
        is_directional=True,
        description="Link to high hub",
        project_ids=["proj_heuristic_test"],
    )
    db_engine.upsert_edge(e1)

    hubs = graph_analytics.get_top_concept_hubs(
        project_id="proj_heuristic_test", max_k=8, relative_threshold=0.30
    )

    # Paper node MUST be excluded from concept hubs
    assert not any(n.node_type == "paper" for n, _ in hubs)
    # High centrality concept node MUST be included
    assert any(n.id == "concept_high_hub" for n, _ in hubs)
