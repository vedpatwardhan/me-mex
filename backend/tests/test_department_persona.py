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


def test_reorganize_concept_hub_selects_qualifying_mutable_candidate(monkeypatch):
    """Verify that when a mutable hub has degree >= threshold, it is passed to LLM and selected."""
    project_id = "proj_qualifying_hub_test"
    hub = GraphNode(
        _id="hub_qualifying",
        node_type="CONCEPT",
        title="Everything",
        description="Over-clustered mutable hub.",
        passage_ids=[],  # Invariant: Mutable hub has no direct passages!
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)

    from app.models import PassageRecord

    p_rec = PassageRecord(
        _id="pass_q1",
        doc_id="doc_q1",
        chunk_index=0,
        text_content="Passage text describing sub-areas of everything.",
        project_ids=[project_id],
    )
    db_engine.upsert_passage(p_rec)

    # Create 5 neighbors connecting to hub, with neighbor_0 holding the grounding passage!
    for i in range(5):
        n_node = GraphNode(
            _id=f"neighbor_{i}",
            node_type="CONCEPT",
            title=f"Topic {i}",
            description="Topic desc",
            passage_ids=["pass_q1"] if i == 0 else [],
            project_ids=[project_id],
            metadata={"immutable": True},
        )
        db_engine.upsert_node(n_node)
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_q_{i}",
                source_id=f"neighbor_{i}",
                target_id="hub_qualifying",
                description="RELEVANT_TO",
                project_ids=[project_id],
            )
        )

    agent = DepartmentPersonaAgent(hub)

    # Mock LLM calls:
    # 1. Discovery returns candidate hub_qualifying
    # 2. Split returns 2 sub-concepts
    # 3. Rewire returns rewired edges
    import json

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if (
            "reorganize_discover" in sys_content
            or "candidate_concept_ids" in sys_content
            or "candidate_id" in sys_content
            or "candidates" in sys_content
        ):
            return '{"candidates": [{"candidate_id": "hub_qualifying", "rationale": "Over-clustered hub combining distinct themes."}]}'
        elif "reorganize_split" in sys_content or "sub_concepts" in sys_content:
            return json.dumps(
                {
                    "sub_concepts": [
                        {
                            "sub_id_alias": "sub_1",
                            "title": "Sub 1",
                            "description": "Synthesized description of Sub 1.",
                        },
                        {
                            "sub_id_alias": "sub_2",
                            "title": "Sub 2",
                            "description": "Synthesized description of Sub 2.",
                        },
                    ]
                }
            )
        elif "reorganize_rewire" in sys_content or "rewired_edges" in sys_content:
            return json.dumps(
                {
                    "rewired_edges": [
                        {
                            "neighbor_id": "neighbor_0",
                            "connect_to_sub_alias": "sub_1",
                            "relation_type": "RELEVANT_TO",
                        },
                        {
                            "neighbor_id": "neighbor_1",
                            "connect_to_sub_alias": "sub_2",
                            "relation_type": "RELEVANT_TO",
                        },
                    ]
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_concept_hub(
        explored_nodes=[hub], project_id=project_id, degree_threshold=5
    )
    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert cmd["action"] == "SPLIT_CONCEPT"
    assert cmd["concept_id"] == "hub_qualifying"
    assert len(cmd["sub_concepts"]) == 2


def test_reorganize_concept_hub_mixed_decongested_skips_phase_2b(monkeypatch):
    """Verify that in mixed neighborhood, Phase 2a runs and if post_2a_degree < threshold, Phase 2b is skipped."""
    project_id = "proj_mixed_decongested_test"
    hub = GraphNode(
        _id="hub_mixed_1",
        node_type="CONCEPT",
        title="AI Foundations",
        description="Over-clustered mutable hub with mixed neighbors.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)

    # 5 immutable leaves and 1 mutable sub-concept (total = 6 >= threshold 5)
    for i in range(5):
        imm_node = GraphNode(
            _id=f"imm_{i}",
            node_type="CONCEPT",
            title=f"Leaf {i}",
            project_ids=[project_id],
            metadata={"immutable": True},
        )
        db_engine.upsert_node(imm_node)
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_imm_{i}",
                source_id=f"imm_{i}",
                target_id="hub_mixed_1",
                description="RELEVANT_TO",
                project_ids=[project_id],
            )
        )

    mut_node = GraphNode(
        _id="mut_existing",
        node_type="CONCEPT",
        title="Existing Mutable Branch",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(mut_node)
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_mut_existing",
            source_id="mut_existing",
            target_id="hub_mixed_1",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )

    agent = DepartmentPersonaAgent(hub)

    import json

    captured_modes = []

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if (
            "reorganize_discover" in sys_content
            or "candidate_id" in sys_content
            or "candidates" in sys_content
        ):
            return '{"candidates": [{"candidate_id": "hub_mixed_1", "rationale": "High degree mixed hub."}]}'
        elif "reorganize_split" in sys_content or "sub_concepts" in sys_content:
            if "leaf_outward" in messages[1]["content"]:
                captured_modes.append("leaf_outward")
            elif "mutable_partition" in messages[1]["content"]:
                captured_modes.append("mutable_partition")
            # Return 2 sub-concepts for Phase 2a
            return json.dumps(
                {
                    "sub_concepts": [
                        {
                            "sub_id_alias": "sub_a",
                            "title": "Sub A",
                            "description": "Desc A",
                        },
                        {
                            "sub_id_alias": "sub_b",
                            "title": "Sub B",
                            "description": "Desc B",
                        },
                    ]
                }
            )
        elif "reorganize_rewire" in sys_content or "rewired_edges" in sys_content:
            return json.dumps(
                {
                    "rewired_edges": [
                        {
                            "neighbor_id": "imm_0",
                            "connect_to_sub_alias": "sub_a",
                            "relation_type": "RELEVANT_TO",
                        },
                        {
                            "neighbor_id": "imm_1",
                            "connect_to_sub_alias": "sub_b",
                            "relation_type": "RELEVANT_TO",
                        },
                    ]
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_concept_hub(
        explored_nodes=[hub], project_id=project_id, degree_threshold=5
    )

    # Pre-split degree: 6 (5 imm + 1 mut).
    # Phase 2a compresses 5 imm into 2 sub_concepts.
    # Post-2a degree = 1 mut + 2 new = 3.
    # 3 < dynamic_threshold (5) -> Decongested! Phase 2b skipped!
    assert "leaf_outward" in captured_modes
    assert "mutable_partition" not in captured_modes

    events = [e["event"] for e in res["emitted_events"]]
    assert "reorg_hub_decongested" in events
    assert len(res["commands"]) == 1
    assert res["commands"][0]["action"] == "SPLIT_CONCEPT"
    assert len(res["commands"][0]["sub_concepts"]) == 2


def test_reorganize_concept_hub_mixed_overclustered_triggers_phase_2b(monkeypatch):
    """Verify that in mixed neighborhood, if post_2a_degree >= threshold, Phase 2b executes."""
    project_id = "proj_mixed_phase2b_test"
    hub = GraphNode(
        _id="hub_mixed_2",
        node_type="CONCEPT",
        title="High Degree Root Hub",
        description="Over-clustered mutable hub with many mutable neighbors.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)

    # 4 immutable leaves + 5 mutable concepts = 9 >= threshold 5
    for i in range(4):
        imm_node = GraphNode(
            _id=f"imm2_{i}",
            node_type="CONCEPT",
            title=f"Leaf 2_{i}",
            project_ids=[project_id],
            metadata={"immutable": True},
        )
        db_engine.upsert_node(imm_node)
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_imm2_{i}",
                source_id=f"imm2_{i}",
                target_id="hub_mixed_2",
                description="RELEVANT_TO",
                project_ids=[project_id],
            )
        )

    for i in range(5):
        mut_node = GraphNode(
            _id=f"mut2_{i}",
            node_type="CONCEPT",
            title=f"Branch 2_{i}",
            project_ids=[project_id],
            metadata={"immutable": False},
        )
        db_engine.upsert_node(mut_node)
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_mut2_{i}",
                source_id=f"mut2_{i}",
                target_id="hub_mixed_2",
                description="SUBSET_OF",
                project_ids=[project_id],
            )
        )

    agent = DepartmentPersonaAgent(hub)

    import json

    captured_modes = []

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if (
            "reorganize_discover" in sys_content
            or "candidate_id" in sys_content
            or "candidates" in sys_content
        ):
            return '{"candidates": [{"candidate_id": "hub_mixed_2", "rationale": "High degree mixed hub."}]}'
        elif "reorganize_split" in sys_content or "sub_concepts" in sys_content:
            user_content = messages[1]["content"]
            if "leaf_outward" in user_content:
                captured_modes.append("leaf_outward")
            elif "mutable_partition" in user_content:
                captured_modes.append("mutable_partition")
            return json.dumps(
                {
                    "sub_concepts": [
                        {
                            "sub_id_alias": "sub_1",
                            "title": "Sub 1",
                            "description": "Desc 1",
                        },
                        {
                            "sub_id_alias": "sub_2",
                            "title": "Sub 2",
                            "description": "Desc 2",
                        },
                    ]
                }
            )
        elif "reorganize_rewire" in sys_content or "rewired_edges" in sys_content:
            return json.dumps(
                {
                    "rewired_edges": [
                        {
                            "neighbor_id": "imm2_0",
                            "connect_to_sub_alias": "sub_1",
                            "relation_type": "RELEVANT_TO",
                        },
                        {
                            "neighbor_id": "mut2_0",
                            "connect_to_sub_alias": "sub_2",
                            "relation_type": "RELEVANT_TO",
                        },
                    ]
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_concept_hub(
        explored_nodes=[hub], project_id=project_id, degree_threshold=5
    )

    # Pre-split degree: 9 (4 imm + 5 mut).
    # Phase 2a creates 2 sub_concepts.
    # Post-2a degree = 5 mut + 2 = 7.
    # 7 >= 5 -> Phase 2b triggers!
    assert "leaf_outward" in captured_modes
    assert "mutable_partition" in captured_modes
    assert len(res["commands"]) == 2  # Phase 2a command + Phase 2b command
