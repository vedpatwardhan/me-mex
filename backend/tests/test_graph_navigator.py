"""
Test Suite: Graph Navigator tree traversal & reorganization

Aligned with docs/ARCHITECTURE.md Section 4:
- Validates Genesis-rooted mutable tree traversal (`traverse_mutable_tree_from_genesis`).
- Validates Root Node Traversal Blocking (Root Nodes provide summary context, but expansion past Root Nodes is strictly blocked).
- Validates passage-grounded hub reorganization (`reorganize_overclustered_nodes`).
"""

import pytest
from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.services.graph_analytics import MutableTreeIndex

pytestmark = pytest.mark.xdist_group(name="worker1")


def test_graph_navigator_shared_exploration():
    """Verify GraphNavigator.traverse_mutable_tree_from_genesis performs tree traversal up to max_depth."""
    hub_node = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="World Models",
        description="World models domain hub.",
        passage_ids=[],
        project_ids=["global"],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub_node)

    agent = GraphNavigator("global")
    exploration = agent.traverse_mutable_tree_from_genesis(
        query="world models research",
        chat_history=[{"role": "user", "content": "Tell me about world models"}],
        allow_web_search=False,
        project_id="global",
    )

    assert exploration["department_id"] == "nav_concept_genesis"
    assert exploration["genesis_node_id"] == "concept_genesis"
    assert "concept_genesis" in exploration["traversed_node_ids"]
    assert len(exploration["traversed_node_ids"]) >= 1
    assert "explored_nodes" in exploration


def test_graph_navigator_root_node_traversal_blocking():
    """Verify traversal visits Root Nodes for context but blocks expanding further hops through them."""
    from app.services.llm_gateway import llm_gateway

    if not llm_gateway.is_server_available():
        print(
            "  ⏭️ test_graph_navigator_root_node_traversal_blocking [SKIPPED - vLLM Server Offline]"
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

    agent = GraphNavigator("global")
    exploration = agent.traverse_mutable_tree_from_genesis(
        query="Explore Hub A",
        project_id="proj_root_blocking_test",
        max_depth=3,
    )

    traversed = exploration["traversed_node_ids"]
    # Hub A and Paper Root are visited...
    assert "concept_hub_a" in traversed
    # ...but traversal past Paper Root to Concept E is strictly BLOCKED!
    assert "concept_e_unreachable" not in traversed


def test_mutable_tree_candidates_exclude_non_subset_mutable_edges():
    """Tree traversal candidates include SUBSET_OF children only, not lateral mutable edges."""
    hub_a = GraphNode(
        _id="hub_a_tree",
        node_type="CONCEPT",
        project_ids=["global"],
        metadata={"immutable": False},
        title="Model-Based Reinforcement Learning",
        description="Core domain hub for model-based RL.",
    )
    c_inside = GraphNode(
        _id="concept_inside_tree",
        node_type="CONCEPT",
        project_ids=["global"],
        metadata={"immutable": False},
        title="Model Predictive Control Planning",
        description="MPC over predicted world model states.",
    )
    c_outside = GraphNode(
        _id="concept_outside_tree",
        node_type="CONCEPT",
        project_ids=["global"],
        metadata={"immutable": False},
        title="Unrelated Lateral Concept",
        description="Linked via PARALLEL_TO, not tree child.",
    )
    db_engine.upsert_node(hub_a)
    db_engine.upsert_node(c_inside)
    db_engine.upsert_node(c_outside)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_tree_1",
            source_id="concept_inside_tree",
            target_id="hub_a_tree",
            description="SUBSET_OF",
            project_ids=["global"],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_tree_2",
            source_id="hub_a_tree",
            target_id="concept_outside_tree",
            description="PARALLEL_TO",
            project_ids=["global"],
        )
    )

    agent = GraphNavigator("global")
    candidates = agent.get_tree_mutable_candidates(
        frontier_ids=["hub_a_tree"],
        tree=MutableTreeIndex(project_id="global"),
        visited_ids=set(),
    )
    assert "concept_inside_tree" in candidates
    assert "concept_outside_tree" not in candidates


def test_reorganize_overclustered_nodes_emits_telemetry_events(monkeypatch):
    """Verify that GraphNavigator.reorganize_overclustered_nodes emits discovery telemetry

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
    agent = GraphNavigator("global")

    # 1. Empty explored nodes
    res_empty = agent.reorganize_overclustered_nodes(
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
    res = agent.reorganize_overclustered_nodes(
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


def test_reorganize_overclustered_nodes_selects_qualifying_mutable_candidate(
    monkeypatch,
):
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

    agent = GraphNavigator("global")

    import json

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if (
            "reorganize_discover" in sys_content
            or "candidate_concept_indices" in sys_content
            or "candidate_index" in sys_content
            or "candidates" in sys_content
        ):
            return '{"candidates": [{"candidate_index": 1, "rationale": "Over-clustered hub combining distinct themes."}]}'
        if "unified partition" in sys_content.lower():
            return json.dumps(
                {
                    "parent_title": "Everything",
                    "parent_description": "Universal domain hub updated to accommodate all sub-concepts.",
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
                    ],
                    "rewired_edges": [
                        {
                            "neighbor_index": i,
                            "connect_to_sub_alias": "sub_1" if i % 2 else "sub_2",
                            "relation_type": "RELEVANT_TO",
                            "description": "Re-wired.",
                        }
                        for i in range(1, 6)
                    ],
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub], project_id=project_id, degree_threshold=5
    )
    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert cmd["action"] == "SPLIT_CONCEPT"
    assert cmd["concept_id"] == "hub_qualifying"
    assert len(cmd["sub_concepts"]) == 2


def test_reorganize_overclustered_nodes_mixed_neighborhood_single_max_coverage_split(
    monkeypatch,
):
    """Mixed mutable+immutable neighbors produce one max_coverage SPLIT_CONCEPT command."""
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

    agent = GraphNavigator("global")

    import json

    captured_modes = []

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if (
            "reorganize_discover" in sys_content
            or "candidate_index" in sys_content
            or "candidates" in sys_content
        ):
            return '{"candidates": [{"candidate_index": 1, "rationale": "High degree mixed hub."}]}'
        if "unified partition" in sys_content.lower():
            if "max_coverage" in messages[1]["content"]:
                captured_modes.append("max_coverage")
            return json.dumps(
                {
                    "parent_title": "AI Foundations & Generative Models",
                    "parent_description": "Overarching domain accommodating Sub A and Sub B.",
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
                    ],
                    "rewired_edges": [
                        {
                            "neighbor_index": i,
                            "connect_to_sub_alias": "sub_a" if i <= 3 else "sub_b",
                            "relation_type": "RELEVANT_TO",
                            "description": "Re-wired.",
                        }
                        for i in range(1, 7)
                    ],
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub], project_id=project_id, degree_threshold=5
    )

    assert "max_coverage" in captured_modes
    assert len(res["commands"]) == 1
    assert res["commands"][0]["action"] == "SPLIT_CONCEPT"
    assert len(res["commands"][0]["sub_concepts"]) == 2


def test_graph_navigator_subgraph_expansion_blocks_immutable_frontier(monkeypatch):
    """Verify GraphNavigator traversal presents immutables for context but blocks them from the frontier."""
    import json

    project_id = "proj_immutable_guard_test"

    hub = GraphNode(
        _id="hub_domain",
        node_type="CONCEPT",
        title="Domain Hub",
        description="Domain hub concept",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    imm_leaf = GraphNode(
        _id="imm_evidence",
        node_type="CONCEPT",
        title="Immutable Evidence",
        description="Factual evidence leaf",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    mut_branch = GraphNode(
        _id="mut_branch",
        node_type="CONCEPT",
        title="Mutable Sub-Domain",
        description="Mutable sub-domain concept",
        project_ids=[project_id],
        metadata={"immutable": False},
    )

    db_engine.upsert_node(hub)
    db_engine.upsert_node(imm_leaf)
    db_engine.upsert_node(mut_branch)

    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_hub_to_imm",
            source_id="hub_domain",
            target_id="imm_evidence",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_hub_to_mut",
            source_id="hub_domain",
            target_id="mut_branch",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )

    agent = GraphNavigator("global")

    # Verify candidate neighbors has explicit immutable flags
    adj_map = agent._get_adjacency_map(project_id)
    candidates = agent.get_candidate_neighbors(
        frontier_ids=[hub.id],
        adj_map=adj_map,
        visited_ids={hub.id},
    )
    assert candidates["imm_evidence"]["immutable"] is True
    assert candidates["mut_branch"]["immutable"] is False

    # Mock chat completion where the model attempts to select both neighbors
    captured_prompt = []

    def mock_chat_completion(messages, **kwargs):
        captured_prompt.append(messages[-1]["content"])
        return json.dumps(
            {
                "selected_neighbors": [
                    {"neighbor_index": 1, "rationale": "Selected neighbor 1"},
                    {"neighbor_index": 2, "rationale": "Selected neighbor 2"},
                ]
            }
        )

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.traverse_mutable_tree_from_genesis(
        query="Test query",
        project_id=project_id,
        max_depth=1,
    )

    # Verify immutable node is tagged in prompt
    assert len(captured_prompt) == 1
    assert '"immutable": true' in captured_prompt[0]
    assert '"immutable": false' in captured_prompt[0]

    # Verify the defensive guard dropped the immutable node from traversal
    assert "imm_evidence" not in res["traversed_node_ids"]
    assert "mut_branch" in res["traversed_node_ids"]


def test_reorganize_overclustered_nodes_updates_parent_hub_title_and_description(
    monkeypatch,
):
    """Verify that SPLIT_CONCEPT updates parent hub title & description to accommodate new sub-concepts."""
    from app.services.graph_ingestion_engine import GraphIngestionEngine

    project_id = "proj_hub_generalize_test"
    tree_parent = GraphNode(
        _id="hub_tree_parent",
        node_type="CONCEPT",
        title="Tree Parent",
        description="Parent in mutable tree.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    parent_hub = GraphNode(
        _id="hub_specialized",
        node_type="CONCEPT",
        title="Specific Narrow Dynamics",
        description="Narrow description before reorganization.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(tree_parent)
    db_engine.upsert_node(parent_hub)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_hub_parent",
            source_id="hub_specialized",
            target_id="hub_tree_parent",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )

    split_cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_specialized",
        "parent_title": "Comprehensive World Modeling Dynamics",
        "parent_description": "Overarching domain accommodating perception, prediction, and control sub-concepts.",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Perceptual Modeling",
                "description": "Sub-concept for perception.",
            },
            {
                "sub_id_alias": "sub_2",
                "title": "Action Refinement",
                "description": "Sub-concept for action optimization.",
            },
        ],
        "rewired_edges": [],
    }

    engine = GraphIngestionEngine()
    engine.execute_single_command(
        split_cmd, doc_title="Test Doc", proj_list=[project_id]
    )

    updated_node = db_engine.get_node("hub_specialized")
    assert updated_node is not None
    assert updated_node.title == "Comprehensive World Modeling Dynamics"
    assert (
        updated_node.description
        == "Overarching domain accommodating perception, prediction, and control sub-concepts."
    )


def test_reorganize_overclustered_nodes_caps_subconcepts_to_half_degree(monkeypatch):
    """Verify that formulated sub-concepts are strictly capped to max(2, n // 2) for compression."""
    import json

    project_id = "proj_cap_half_degree_test"
    hub = GraphNode(
        _id="hub_test_cap",
        node_type="CONCEPT",
        title="Over-clustered Hub",
        description="Hub with 5 immutable leaves.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)

    for i in range(5):
        imm_node = GraphNode(
            _id=f"imm_cap_{i}",
            node_type="CONCEPT",
            title=f"Leaf {i}",
            project_ids=[project_id],
            metadata={"immutable": True},
        )
        db_engine.upsert_node(imm_node)
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_cap_{i}",
                source_id=f"imm_cap_{i}",
                target_id="hub_test_cap",
                description="RELEVANT_TO",
                project_ids=[project_id],
            )
        )

    agent = GraphNavigator("global")

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if "reorganize_discover" in sys_content or "candidates" in sys_content:
            return (
                '{"candidates": [{"candidate_index": 1, "rationale": "Degree >= 5"}]}'
            )
        if "unified partition" in sys_content.lower():
            return json.dumps(
                {
                    "parent_title": "Generalized Umbrella Hub",
                    "parent_description": "Accommodating all sub-concepts.",
                    "sub_concepts": [
                        {
                            "sub_id_alias": f"sub_{i}",
                            "title": f"Sub {i}",
                            "description": f"Desc {i}",
                        }
                        for i in range(4)
                    ],
                    "rewired_edges": [
                        {
                            "neighbor_index": i + 1,
                            "connect_to_sub_alias": f"sub_{i}",
                            "relation_type": "RELEVANT_TO",
                            "description": "Re-wired.",
                        }
                        for i in range(5)
                    ],
                }
            )
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub],
        project_id=project_id,
        degree_threshold=5,
    )

    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert cmd["action"] == "SPLIT_CONCEPT"
    # For n = 5 neighbors, max allowed sub-concepts is 5 // 2 = 2
    assert len(cmd["sub_concepts"]) == 2


def test_cap_sub_concepts_and_remap_rewires():
    from app.agents.graph_navigator import _cap_sub_concepts_and_remap_rewires

    subs = [{"sub_id_alias": f"sub_{i}"} for i in range(4)]
    rewires = [
        {
            "neighbor_index": i + 1,
            "connect_to_sub_alias": f"sub_{i}",
            "relation_type": "RELEVANT_TO",
        }
        for i in range(4)
    ]
    capped_subs, capped_rewires = _cap_sub_concepts_and_remap_rewires(
        subs, rewires, max_allowed_subs=2, overflow_alias="ANCESTOR"
    )
    assert len(capped_subs) == 2
    assert capped_subs[0]["sub_id_alias"] == "sub_0"
    assert capped_subs[1]["sub_id_alias"] == "sub_1"
    for edge in capped_rewires:
        assert edge["connect_to_sub_alias"] in ("sub_0", "sub_1", "ANCESTOR")


def test_reorg_partition_prompt_injects_strategy_without_jinja():
    from app.agents.graph_navigator import _reorg_split_strategy_block
    from app.prompts import load_prompt

    block, overflow = _reorg_split_strategy_block(is_genesis=True)
    prompt = load_prompt(
        "graph_reorg_partition",
        department_name="Graph Navigator",
        node_id="concept_genesis",
        mode="max_coverage",
        split_strategy_block=block,
        overflow_alias=overflow,
        min_allowed_sub_concepts=2,
        max_allowed_sub_concepts=3,
        neighbor_count=7,
    )
    assert "{%" not in prompt
    assert "WRAPPER SPLIT" in prompt
    assert "EVERYTHING" in prompt

    block_r, overflow_r = _reorg_split_strategy_block(is_genesis=False)
    prompt_r = load_prompt(
        "graph_reorg_partition",
        department_name="Graph Navigator",
        node_id="hub_x",
        mode="max_coverage",
        split_strategy_block=block_r,
        overflow_alias=overflow_r,
        min_allowed_sub_concepts=2,
        max_allowed_sub_concepts=3,
        neighbor_count=7,
    )
    assert "REPLACEMENT SPLIT" in prompt_r
    assert "sub_1" in prompt_r
    assert "ANCESTOR" in prompt_r
