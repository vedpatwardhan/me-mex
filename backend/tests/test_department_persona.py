"""
Test Suite: Department Persona Agent Sub-Graph Exploration & Reorganization

Aligned with docs/ARCHITECTURE.md Section 4:
- Validates sub-graph traversal (`explore_concept_hub`) over mutually exclusive partitions.
- Validates Root Node Traversal Blocking (Root Nodes provide summary context, but expansion past Root Nodes is strictly blocked).
- Validates independent passage-grounded concept node reorganization (`reorganize_concept_hub`).
"""

import pytest
from app.agents.department_persona import DepartmentPersonaAgent
from app.db import db_engine
from app.models import GraphNode, GraphEdge

pytestmark = pytest.mark.xdist_group(name="worker1")


def test_department_persona_shared_exploration():
    """Verify DepartmentPersonaAgent.explore_concept_hub performs sub-graph traversal up to max_depth."""
    hub_node = GraphNode(
        _id="concept_world_models_test",
        node_type="CONCEPT",
        title="World Models",
        description="World models domain hub.",
        passage_ids=[],
        project_ids=["global"],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub_node)

    agent = DepartmentPersonaAgent(hub_node)
    exploration = agent.explore_concept_hub(
        query="world models research",
        chat_history=[{"role": "user", "content": "Tell me about world models"}],
        allow_web_search=False,
        project_id="global",
    )

    assert exploration["department_id"] == "dept_concept_world_models_test"
    assert exploration["hub_node_id"] == "concept_world_models_test"
    assert "concept_world_models_test" in exploration["traversed_node_ids"]
    assert "explored_nodes" in exploration


def test_department_persona_root_node_traversal_blocking():
    """Verify traversal visits Root Nodes for context but blocks expanding further hops through them."""
    from app.services.llm_gateway import llm_gateway

    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_department_persona_root_node_traversal_blocking [SKIPPED - vLLM Server Offline]"
        )
        return
    hub_a = GraphNode(
        _id="concept_hub_a",
        node_type="CONCEPT",
        title="Hub Concept A",
        project_ids=["proj_root_blocking_test"],
        metadata={"immutable": False},
    )
    paper_root = GraphNode(
        _id="paper_d_root",
        node_type="ROOT",  # ROOT NODE
        title="Paper D Container",
        project_ids=["proj_root_blocking_test"],
        metadata={"immutable": True},
    )
    concept_e = GraphNode(
        _id="concept_e_unreachable",
        node_type="CONCEPT",
        title="Concept E from Paper D",
        project_ids=["proj_root_blocking_test"],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(hub_a)
    db_engine.upsert_node(paper_root)
    db_engine.upsert_node(concept_e)

    # Edge Hub A -> Paper Root
    e1 = GraphEdge(
        _id="edge_a_to_d",
        source_id="concept_hub_a",
        target_id="paper_d_root",
        is_directional=True,
        description="Hub A extracted from Paper Root",
        project_ids=["proj_root_blocking_test"],
    )
    # Edge Paper Root -> Concept E
    e2 = GraphEdge(
        _id="edge_d_to_e",
        source_id="paper_d_root",
        target_id="concept_e_unreachable",
        is_directional=True,
        description="Paper Root contains Concept E",
        project_ids=["proj_root_blocking_test"],
    )
    db_engine.upsert_edge(e1)
    db_engine.upsert_edge(e2)

    agent = DepartmentPersonaAgent(hub_a)
    exploration = agent.explore_concept_hub(
        query="Explore Hub A",
        project_id="proj_root_blocking_test",
        max_depth=3,
    )

    traversed = exploration["traversed_node_ids"]
    # Hub A and Paper Root are visited...
    assert "concept_hub_a" in traversed
    # ...but traversal past Paper Root to Concept E is strictly BLOCKED!
    assert "concept_e_unreachable" not in traversed


@pytest.mark.vllm
def test_department_persona_mutually_exclusive_partitioning():
    """Verify DepartmentPersonaAgent.explore_concept_hub strictly obeys partition_node_ids boundaries."""
    from app.services.llm_gateway import llm_gateway

    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_department_persona_mutually_exclusive_partitioning [SKIPPED - vLLM Server Offline]"
        )
        return

    hub_a = GraphNode(
        _id="hub_a",
        node_type="CONCEPT",
        project_ids=["proj_partition_test"],
        metadata={"immutable": False},
        title="Model-Based Reinforcement Learning",
        description="Core domain hub for model-based RL and trajectory planning.",
    )
    c_inside = GraphNode(
        _id="concept_inside_partition",
        node_type="CONCEPT",
        project_ids=["proj_partition_test"],
        metadata={"immutable": False},
        title="Model Predictive Control Planning",
        description="MPC optimizes action sequences over predicted world model states.",
    )
    c_outside = GraphNode(
        _id="concept_outside_partition",
        node_type="CONCEPT",
        project_ids=["proj_partition_test"],
        metadata={"immutable": False},
        title="Unrelated Concept Outside Partition",
        description="Unrelated concept outside the assigned partition.",
    )

    db_engine.upsert_node(hub_a)
    db_engine.upsert_node(c_inside)
    db_engine.upsert_node(c_outside)

    db_engine.upsert_edge(
        GraphEdge(
            _id="e1",
            source_id="hub_a",
            target_id="concept_inside_partition",
            description="SUBSET_OF",
            project_ids=["proj_partition_test"],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e2",
            source_id="hub_a",
            target_id="concept_outside_partition",
            description="PARALLEL_TO",
            project_ids=["proj_partition_test"],
        )
    )

    agent = DepartmentPersonaAgent(hub_a)

    # Restrict partition strictly to {"hub_a", "concept_inside_partition"}
    partition = {"hub_a", "concept_inside_partition"}
    exploration = agent.explore_concept_hub(
        query="test partition",
        project_id="proj_partition_test",
        max_depth=3,
        partition_node_ids=partition,
    )

    traversed = exploration["traversed_node_ids"]
    assert "hub_a" in traversed
    assert "concept_inside_partition" in traversed
    # concept_outside_partition MUST be excluded because it is outside partition boundary!
    assert "concept_outside_partition" not in traversed


def test_reorganize_concept_hub_emits_telemetry_events(monkeypatch):
    """Verify that DepartmentPersonaAgent.reorganize_concept_hub emits discovery telemetry

    events even when no nodes qualify or when explored_nodes is empty.
    """
    hub = GraphNode(
        _id="hub_telemetry",
        node_type="CONCEPT",
        title="Telemetry Hub",
        description="Testing reorganization telemetry.",
        passage_ids=[],
        project_ids=["proj_reorg_telemetry"],
        metadata={"immutable": False},
    )
    agent = DepartmentPersonaAgent(hub)

    # 1. Empty explored nodes
    res_empty = agent.reorganize_concept_hub(
        explored_nodes=[], project_id="proj_reorg_telemetry"
    )
    assert res_empty["commands"] == []
    assert res_empty["emitted_events"] == []

    # 2. Mock discovery LLM response returning 0 candidate IDs
    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(
        llm_gateway,
        "generate_chat_completion",
        lambda *args, **kwargs: '{"candidate_concept_ids": []}',
    )

    db_engine.upsert_node(hub)
    res = agent.reorganize_concept_hub(
        explored_nodes=[hub], project_id="proj_reorg_telemetry", degree_threshold=5
    )
    events = res.get("emitted_events", [])
    assert len(events) == 2
    event_names = [e["event"] for e in events]
    assert "reorg_discovery_started" in event_names
    assert "reorg_discovery_completed" in event_names
    start_evt = next(e for e in events if e["event"] == "reorg_discovery_started")
    assert start_evt["qualifying_candidates_count"] == 0
    assert start_evt["evaluated_nodes_count"] == 1
    done_evt = next(e for e in events if e["event"] == "reorg_discovery_completed")
    assert done_evt["candidate_count"] == 0
    assert "cohesive" in done_evt["message"]
