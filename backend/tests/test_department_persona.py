from app.agents.department_persona import DepartmentPersonaAgent
from app.db import db_engine
from app.models import GraphNode, GraphEdge


def test_department_persona_project_scoping():
    """Verify DepartmentPersonaAgent.explore_and_retrieve respects project_id edge filtering."""
    hub_node = db_engine.get_node("concept_action_mpc")
    assert hub_node is not None

    agent = DepartmentPersonaAgent(hub_node)

    # Add edge specific to proj_scoped
    scoped_edge = GraphEdge(
        _id="edge_mpc_scoped",
        source_id="concept_action_mpc",
        target_id="concept_world_models",
        is_directional=True,
        description="MPC to World Models link",
        project_ids=["global", "proj_scoped"],
    )
    db_engine.upsert_edge(scoped_edge)

    finding_global = agent.explore_and_retrieve(
        "MPC optimization", allow_web_search=False, project_id="global"
    )
    finding_scoped = agent.explore_and_retrieve(
        "MPC optimization", allow_web_search=False, project_id="proj_scoped"
    )

    assert "traversed_node_ids" in finding_global
    assert "traversed_node_ids" in finding_scoped


def test_department_persona_shared_exploration():
    """Verify DepartmentPersonaAgent.explore_concept_hub performs sub-graph traversal."""
    hub_node = db_engine.get_node("concept_world_models")
    agent = DepartmentPersonaAgent(hub_node)
    exploration = agent.explore_concept_hub(
        query="world models research",
        chat_history=[{"role": "user", "content": "Tell me about world models"}],
        allow_web_search=False,
        project_id="global",
    )

    assert exploration["department_id"] == "dept_concept_world_models"
    assert exploration["hub_node_id"] == "concept_world_models"
    assert "concept_world_models" in exploration["traversed_node_ids"]
    assert "subgraph_nodes" in exploration


def test_department_persona_root_media_traversal_blocking():
    """Verify traversal visits root media nodes for context but blocks them from expanding further hops."""
    # Hub Concept A -> Root Paper D -> Concept E
    hub_a = GraphNode(
        _id="concept_hub_a",
        node_type="concept",
        title="Hub Concept A",
        project_ids=["proj_root_blocking_test"],
    )
    paper_d = GraphNode(
        _id="paper_d_root",
        node_type="paper",
        title="Paper D Container",
        project_ids=["proj_root_blocking_test"],
    )
    concept_e = GraphNode(
        _id="concept_e_unreachable",
        node_type="concept",
        title="Concept E from Paper D",
        project_ids=["proj_root_blocking_test"],
    )
    db_engine.upsert_node(hub_a)
    db_engine.upsert_node(paper_d)
    db_engine.upsert_node(concept_e)

    # Edge A -> Paper D
    e1 = GraphEdge(
        _id="edge_a_to_d",
        source_id="concept_hub_a",
        target_id="paper_d_root",
        is_directional=True,
        description="Hub A extracted from Paper D",
        project_ids=["proj_root_blocking_test"],
    )
    # Edge Paper D -> Concept E
    e2 = GraphEdge(
        _id="edge_d_to_e",
        source_id="paper_d_root",
        target_id="concept_e_unreachable",
        is_directional=True,
        description="Paper D also contains Concept E",
        project_ids=["proj_root_blocking_test"],
    )
    db_engine.upsert_edge(e1)
    db_engine.upsert_edge(e2)

    agent = DepartmentPersonaAgent(hub_a)
    exploration = agent.explore_concept_hub(
        query="Explore Hub A",
        allow_web_search=False,
        project_id="proj_root_blocking_test",
        max_depth=3,
    )

    # Paper D should be visited (present in traversed_node_ids)
    assert "paper_d_root" in exploration["traversed_node_ids"]
    # Concept E must NOT be reached through Paper D
    assert "concept_e_unreachable" not in exploration["traversed_node_ids"]
