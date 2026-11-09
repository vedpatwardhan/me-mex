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


def _partition_payload_json(
    n_neighbors: int,
    num_subs: int = 2,
    parent_title: str = "Umbrella",
    parent_description: str = "Desc",
) -> dict:
    """Valid three-list partition: ≥2 edges per sub, overflow for remainder."""
    num_subs = min(num_subs, max(2, n_neighbors // 2))
    subs = [
        {
            "sub_id_alias": f"sub_{i + 1}",
            "title": f"Sub {i + 1}",
            "description": "Synthesized.",
        }
        for i in range(num_subs)
    ]
    edges = []
    overflow = []
    idx = 1
    for s in range(num_subs):
        alias = f"sub_{s + 1}"
        for _ in range(2):
            if idx > n_neighbors:
                break
            edges.append(
                {
                    "neighbor_index": idx,
                    "connect_to_sub_alias": alias,
                    "description": "Re-wired.",
                }
            )
            idx += 1
    while idx <= n_neighbors:
        overflow.append(
            {
                "neighbor_index": idx,
                "rationale": "Does not fit a ≥2-neighbor sub group.",
            }
        )
        idx += 1
    return {
        "parent_title": parent_title,
        "parent_description": parent_description,
        "sub_concepts": subs,
        "overflow_neighbors": overflow,
        "rewired_edges": edges,
    }


@pytest.mark.vllm
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


@pytest.mark.vllm
def test_graph_navigator_root_node_traversal_blocking():
    """Live vLLM: ROOT nodes may appear in context but must not expand the mutable-tree frontier."""
    project_id = "global"
    hub_a = GraphNode(
        _id="concept_hub_a",
        node_type="CONCEPT",
        title="Hub Concept A",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    paper_root = GraphNode(
        _id="paper_d_root",
        node_type="ROOT",
        title="Paper D Container",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    concept_e = GraphNode(
        _id="concept_e_unreachable",
        node_type="CONCEPT",
        title="Concept E from Paper D",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(hub_a)
    db_engine.upsert_node(paper_root)
    db_engine.upsert_node(concept_e)
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_hub_a_genesis",
            source_id="concept_hub_a",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_a_to_d",
            source_id="concept_hub_a",
            target_id="paper_d_root",
            is_directional=True,
            description="Hub A extracted from Paper Root",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_d_to_e",
            source_id="paper_d_root",
            target_id="concept_e_unreachable",
            is_directional=True,
            description="Paper Root contains Concept E",
            project_ids=[project_id],
        )
    )

    agent = GraphNavigator(project_id)
    exploration = agent.traverse_mutable_tree_from_genesis(
        query="Explore Hub Concept A and its linked paper container",
        project_id=project_id,
        max_depth=3,
    )

    traversed = exploration["traversed_node_ids"]
    assert "concept_genesis" in traversed
    assert "concept_e_unreachable" not in traversed


def test_mutable_tree_candidates_exclude_non_subset_mutable_edges():
    """Tree traversal candidates include mutable tree children only, not lateral mutable edges."""
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


def test_reorganize_overclustered_nodes_emits_telemetry_events():
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

    # 2. Hub with degree below threshold — no vLLM discover call
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


@pytest.mark.vllm
def test_reorganize_overclustered_nodes_selects_qualifying_mutable_candidate():
    """Live vLLM: hub with degree >= threshold yields a valid SPLIT_CONCEPT plan."""
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

    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub],
        project_id=project_id,
        degree_threshold=5,
        plan_only=True,
    )
    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert cmd["action"] == "SPLIT_CONCEPT"
    assert cmd["concept_id"] == "hub_qualifying"
    assert len(cmd["sub_concepts"]) >= 1
    assert len(cmd.get("partition_neighbor_ids") or []) == 5


@pytest.mark.vllm
def test_reorganize_overclustered_nodes_mixed_neighborhood_single_max_coverage_split():
    """Live vLLM: mixed mutable+immutable neighbor batch partitions successfully."""
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

    # 5 immutable leaves and 1 mutable direct neighbor (all in partition batch)
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

    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub],
        project_id=project_id,
        degree_threshold=5,
        plan_only=True,
    )

    assert len(res["commands"]) == 1
    assert res["commands"][0]["action"] == "SPLIT_CONCEPT"
    assert len(res["commands"][0].get("partition_neighbor_ids", [])) == 6
    assert len(res["commands"][0]["sub_concepts"]) >= 1


def test_grouped_traversal_uses_grouped_payload(monkeypatch):
    """Offline: saturated traversal issues GroupedExplorationPayload LLM calls."""
    from app.models import (
        GroupedExplorationPayload,
        GroupedFrontierSelection,
        SelectedNeighborItem,
    )

    project_id = "proj_grouped_trav"
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Genesis scope.",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    child = GraphNode(
        _id="mut_child",
        node_type="CONCEPT",
        title="Decision Models",
        description="Hub",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(genesis)
    db_engine.upsert_node(child)
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_child_genesis",
            source_id="mut_child",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )

    calls = []

    def fake_llm(messages, response_model, **kwargs):
        calls.append(response_model.__name__)
        if response_model is GroupedExplorationPayload:
            return GroupedExplorationPayload(
                frontier_selections=[
                    GroupedFrontierSelection(
                        frontier_index=1,
                        selected_neighbors=[
                            SelectedNeighborItem(neighbor_index=1, rationale="relevant")
                        ],
                    )
                ]
            )
        raise AssertionError(f"unexpected response_model {response_model}")

    monkeypatch.setattr(
        "app.agents.graph_navigator.llm_gateway.generate_structured_completion",
        fake_llm,
    )

    agent = GraphNavigator(project_id)
    out = agent.traverse_mutable_tree_from_genesis(
        query="decision models",
        project_id=project_id,
        max_depth=2,
        traversal_top_k=2,
    )
    assert "GroupedExplorationPayload" in calls
    assert "mut_child" in out["traversed_node_ids"]


@pytest.mark.vllm
def test_graph_navigator_subgraph_expansion_blocks_immutable_frontier():
    """Live vLLM: immutable leaves are not expanded in the traversal frontier."""
    project_id = "proj_immutable_guard_test"

    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
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

    db_engine.upsert_node(genesis)
    db_engine.upsert_node(hub)
    db_engine.upsert_node(imm_leaf)
    db_engine.upsert_node(mut_branch)

    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_hub_genesis",
            source_id="hub_domain",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
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
            _id="edge_mut_to_hub",
            source_id="mut_branch",
            target_id="hub_domain",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )

    agent = GraphNavigator(project_id)

    # Verify candidate neighbors has explicit immutable flags
    adj_map = agent._get_adjacency_map(project_id)
    candidates = agent.get_candidate_neighbors(
        frontier_ids=[hub.id],
        adj_map=adj_map,
        visited_ids={hub.id},
    )
    assert candidates["imm_evidence"]["immutable"] is True
    assert candidates["mut_branch"]["immutable"] is False

    res = agent.traverse_mutable_tree_from_genesis(
        query="Explore the mutable sub-domain branch only",
        project_id=project_id,
        max_depth=2,
    )

    assert "imm_evidence" not in res["traversed_node_ids"]


def test_reorganize_overclustered_nodes_updates_parent_hub_title_and_description():
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
    assert updated_node.title == "Perceptual Modeling"
    assert updated_node.description == "Sub-concept for perception."


@pytest.mark.vllm
def test_reorganize_live_partition_passes_validation_and_emits_plan():
    """Live vLLM discover + partition returns a command and partition_completed telemetry."""
    project_id = "proj_live_partition_smoke"
    hub = GraphNode(
        _id="hub_live_partition",
        node_type="CONCEPT",
        title="Robotics Foundations Hub",
        description="Over-clustered hub for live partition smoke test.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)
    topics = [
        "Trajectory Planning",
        "Perception Stacks",
        "Sim-to-Real Transfer",
        "Benchmark Suites",
        "Safety Constraints",
        "Policy Optimization",
    ]
    for i, title in enumerate(topics, start=1):
        nid = f"imm_live_{i}"
        db_engine.upsert_node(
            GraphNode(
                _id=nid,
                node_type="CONCEPT",
                title=title,
                description=f"Evidence about {title}.",
                project_ids=[project_id],
                metadata={"immutable": True},
            )
        )
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_live_{i}",
                source_id=nid,
                target_id="hub_live_partition",
                description="linked",
                project_ids=[project_id],
            )
        )

    agent = GraphNavigator("global")
    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub],
        project_id=project_id,
        degree_threshold=5,
        plan_only=True,
    )
    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert cmd["action"] == "SPLIT_CONCEPT"
    assert len(cmd.get("partition_neighbor_ids") or []) == len(topics)
    completed = [
        e
        for e in res["emitted_events"]
        if e.get("event") == "reorg_partition_completed"
    ]
    assert len(completed) == 1
    assert completed[0].get("validation_passed") is True


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
        overflow_target_label="Everything (Genesis)",
        min_sub_concepts=1,
        min_sub_neighbors=2,
        max_allowed_sub_concepts=3,
        neighbor_count=7,
    )
    assert "{%" not in prompt
    assert "WRAPPER SPLIT" in prompt
    assert "overflow_neighbors" in prompt
    assert "connect_to_existing_neighbor_index" in prompt
    assert "MIN-2 PER NEW SUB" in prompt

    block_r, _overflow_r = _reorg_split_strategy_block(is_genesis=False)
    prompt_r = load_prompt(
        "graph_reorg_partition",
        department_name="Graph Navigator",
        node_id="hub_x",
        mode="max_coverage",
        split_strategy_block=block_r,
        overflow_target_label="the tree ancestor",
        min_sub_concepts=1,
        min_sub_neighbors=2,
        max_allowed_sub_concepts=3,
        neighbor_count=7,
    )
    assert "REPLACEMENT SPLIT" in prompt_r
    assert "sub_1" in prompt_r
    assert "overflow_neighbors" in prompt_r
    assert "REWIRED_EDGES INVARIANTS" in prompt_r
    assert "must differ from `neighbor_index`" in prompt_r
