from app.agents.department_persona import DepartmentPersonaAgent
from app.db import db_engine
from app.models import GraphEdge


def test_department_persona_project_scoping():
    """Verify DepartmentPersonaAgent.explore_and_debate_retrieval respects project_id edge filtering."""
    hub_node = db_engine.get_node("concept_action_mpc")
    assert hub_node is not None

    agent = DepartmentPersonaAgent(hub_node)

    # Add edge specific to proj_scoped
    scoped_edge = GraphEdge(
        _id="edge_mpc_scoped",
        source_id="concept_action_mpc",
        target_id="concept_world_models",
        is_directional=True,
        text_body="MPC to World Models link",
        project_ids=["global", "proj_scoped"],
    )
    db_engine.upsert_edge(scoped_edge)

    finding_global = agent.explore_and_debate_retrieval(
        "MPC optimization", allow_web_search=False, project_id="global"
    )
    finding_scoped = agent.explore_and_debate_retrieval(
        "MPC optimization", allow_web_search=False, project_id="proj_scoped"
    )

    assert "traversing_node_ids" in finding_global
    assert "traversing_node_ids" in finding_scoped


def test_department_persona_shared_exploration():
    """Verify DepartmentPersonaAgent.explore_and_debate_hub performs sub-graph traversal and relevance debate."""
    hub_node = db_engine.get_node("concept_world_models")
    assert hub_node is not None

    agent = DepartmentPersonaAgent(hub_node)
    exploration = agent.explore_and_debate_hub(
        query="world models research",
        chat_history=[{"role": "user", "content": "Tell me about world models"}],
        allow_web_search=False,
        project_id="global",
    )

    assert exploration["department_id"] == "dept_concept_world_models"
    assert exploration["hub_node_id"] == "concept_world_models"
    assert "concept_world_models" in exploration["traversing_node_ids"]
    assert "subgraph_nodes" in exploration
