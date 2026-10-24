"""
Test Suite: Zero-Consensus Graph Reconciliation & Node Mutability Enforcement

Aligned with docs/ARCHITECTURE.md Section 3 & Section 4:
- Validates independent zero-consensus persona command execution into MongoDB.
- Validates Node Mutability Hierarchy:
    - Root Nodes (`ROOT`) & Intra-Document Concepts (`immutable: True`) CANNOT be modified (`EDIT_CONCEPT`), split (`SPLIT_CONCEPT`), or deleted by persona commands.
    - Persona-created Domain Hubs & Intermediate Nodes (`immutable: False`) can be edited or split when over-clustered.
"""

import time
import pytest
from app.agents.orchestrator import orchestrator
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.agents.department_persona import DepartmentPersonaAgent
from app.models import GraphNode, GraphEdge
from app.db import db_engine

pytestmark = pytest.mark.xdist_group(name="worker1")


def test_independent_ingestion_linking():
    """Verify independent zero-consensus ingestion linking of immutable intra-document concepts to domain hubs."""
    domain_hub_id = "concept_domain_hub_test"
    hub_node = GraphNode(
        _id=domain_hub_id,
        node_type="CONCEPT",
        title="Domain Hub World Models",
        description="Main domain hub for world model research.",
        passage_ids=[],
        project_ids=["global"],
        metadata={"immutable": False},  # Mutable Domain Hub
    )
    db_engine.upsert_node(hub_node)

    intra_concept_id = "concept_intra_doc_test"
    intra_node = GraphNode(
        _id=intra_concept_id,
        node_type="CONCEPT",
        title="Pixel-Based Dynamics",
        description="Extracted intra-document concept.",
        passage_ids=["pass_01"],
        project_ids=["global"],
        metadata={"immutable": True},  # Immutable Intra-Doc Concept
    )
    db_engine.upsert_node(intra_node)

    persona_command_results = [
        {
            "department_name": "Persona Specialist: World Models",
            "commands": [
                {
                    "action": "CREATE_EDGE",
                    "edge": {
                        "source_id": intra_concept_id,
                        "target_id": domain_hub_id,
                        "description": "RELEVANT_TO",
                    },
                }
            ],
        }
    ]

    events = list(
        graph_ingestion_engine.process_persona_ingestion_commands(
            persona_command_results=persona_command_results,
            doc_id="doc_test_linking",
            doc_title="Test Linking Paper",
            consolidated_concepts=[{"title": "Pixel-Based Dynamics"}],
            project_id="global",
        )
    )

    all_edges = db_engine.get_edges(project_id="global")
    link_edge = next(
        (
            e
            for e in all_edges
            if e.source_id == intra_concept_id and e.target_id == domain_hub_id
        ),
        None,
    )
    assert link_edge is not None
    assert link_edge.description == "RELEVANT_TO"


def test_node_immutability_enforcement():
    """Verify that direct mutations (EDIT_CONCEPT, SPLIT_CONCEPT) targeting immutable nodes are strictly blocked."""
    immutable_id = "concept_immutable_factual_node"
    immutable_node = GraphNode(
        _id=immutable_id,
        node_type="CONCEPT",
        title="Ground Truth Factual Evidence",
        description="Original ground truth factual text.",
        passage_ids=["pass_gt_01"],
        project_ids=["global"],
        metadata={"immutable": True},  # IMMUTABLE
    )
    db_engine.upsert_node(immutable_node)

    # Attempt illegal EDIT_CONCEPT command targeting immutable node
    edit_cmd_item = {
        "department_name": "Hostile Persona",
        "action": "EDIT_CONCEPT",
        "concept": {
            "id": immutable_id,
            "title": "Altered Title",
            "description": "Illegal altered text payload.",
        },
    }

    evt = graph_ingestion_engine.execute_single_command(
        item=edit_cmd_item, doc_title="Test Paper", proj_list=["global"]
    )
    assert evt is None  # Command execution blocked

    fetched_node = db_engine.get_node(immutable_id)
    assert fetched_node is not None
    assert fetched_node.title == "Ground Truth Factual Evidence"
    assert fetched_node.description == "Original ground truth factual text."


def test_mutable_concept_node_splitting():
    """Verify independent passage-grounded concept splitting (SPLIT_CONCEPT) on over-clustered mutable domain nodes."""
    mutable_hub_id = "concept_overclustered_domain_node"
    mutable_hub = GraphNode(
        _id=mutable_hub_id,
        node_type="CONCEPT",
        title="Over-Clustered Domain Concept",
        description="General domain concept with too many links.",
        passage_ids=["pass_chunk_101", "pass_chunk_102"],
        project_ids=["global"],
        metadata={"immutable": False},  # MUTABLE
    )
    db_engine.upsert_node(mutable_hub)

    split_cmd_item = {
        "department_name": "Reorg Persona",
        "action": "SPLIT_CONCEPT",
        "concept_id": mutable_hub_id,
        "sub_concepts": [
            {
                "title": "Sub-Concept Alpha",
                "description": "Focused sub-concept Alpha.",
                "passage_ids": ["pass_chunk_101"],
            },
            {
                "title": "Sub-Concept Beta",
                "description": "Focused sub-concept Beta.",
                "passage_ids": ["pass_chunk_102"],
            },
        ],
    }

    evt = graph_ingestion_engine.execute_single_command(
        item=split_cmd_item, doc_title="Test Paper", proj_list=["global"]
    )
    assert evt is not None
    assert evt["event"] == "node_touched"

    # Original over-clustered node PRESERVED as umbrella node!
    old_node = db_engine.get_node(mutable_hub_id)
    assert old_node is not None
    assert old_node.id == mutable_hub_id

    # New focused sub-concepts inserted into DB
    all_nodes = db_engine.get_nodes(project_id="global")
    sub_nodes = [n for n in all_nodes if n.metadata.get("sub_of_hub") == mutable_hub_id]
    assert len(sub_nodes) == 2
    titles = [n.title for n in sub_nodes]
    assert "Sub-Concept Alpha" in titles
    assert "Sub-Concept Beta" in titles


def test_split_concept_rewiring_deletes_old_hub_edge():
    """Verify SPLIT_CONCEPT deletes the old edge between neighbor and original hub when re-wiring to sub-concept."""
    project_id = "test_rewire_proj"

    # Hub node
    hub_node = GraphNode(
        _id="hub_original",
        node_type="CONCEPT",
        title="Everything Hub",
        description="Over-clustered mutable hub.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub_node)

    # Neighbor concept node
    neighbor_node = GraphNode(
        _id="neighbor_concept",
        node_type="CONCEPT",
        title="World Models",
        description="Neighbor concept.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(neighbor_node)

    # Pre-existing edge connecting neighbor to hub
    old_edge = GraphEdge(
        _id="edge_old_neighbor_hub",
        source_id="neighbor_concept",
        target_id="hub_original",
        description="Generic Hub Link",
        project_ids=[project_id],
    )
    db_engine.upsert_edge(old_edge)
    assert len(db_engine.get_edges(project_id)) == 1

    # Split hub and rewire neighbor to sub_1
    split_cmd_item = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_original",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "World Models Focus",
                "description": "Specific sub-concept",
                "passage_ids": [],
            }
        ],
        "rewired_edges": [
            {
                "neighbor_id": "neighbor_concept",
                "connect_to_sub_alias": "sub_1",
                "relation_type": "SUBSET_OF",
            }
        ],
    }

    graph_ingestion_engine.execute_single_command(
        item=split_cmd_item, doc_title="Test Doc", proj_list=[project_id]
    )

    all_edges = db_engine.get_edges(project_id)
    # Expected edges:
    # 1. sub_1 -> hub_original (SUBSET_OF umbrella edge)
    # 2. neighbor_concept -> sub_1 (rewired edge)
    # The old edge neighbor_concept -> hub_original MUST have been deleted!
    assert len(all_edges) == 2
    direct_hub_edges = [
        e
        for e in all_edges
        if (e.source_id == "neighbor_concept" and e.target_id == "hub_original")
        or (e.source_id == "hub_original" and e.target_id == "neighbor_concept")
    ]
    assert len(direct_hub_edges) == 0, "Old edge to original hub was not deleted!"

    sub_rewired_edges = [
        e
        for e in all_edges
        if e.source_id == "neighbor_concept" and e.target_id != "hub_original"
    ]
    assert len(sub_rewired_edges) == 1
    assert sub_rewired_edges[0].description == "SUBSET_OF"


def test_split_concept_rewire_multi_subconcept_connections():
    """Verify that a single neighbor can be cleanly re-wired to MULTIPLE sub-concepts,

    old umbrella edges are deleted once, and no sub-concept is left idle.
    """
    project_id = "test_multi_rewire_project"

    # Hub node
    hub_node = GraphNode(
        _id="hub_multi",
        node_type="CONCEPT",
        title="Multi-Domain Hub",
        description="Over-clustered hub to split.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub_node)

    # Neighbor concept node that is relevant to multiple sub-concepts
    neighbor_node = GraphNode(
        _id="neighbor_shared_eval",
        node_type="CONCEPT",
        title="Benchmark Evaluations",
        description="Evaluation protocol relevant to multiple sub-domains.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(neighbor_node)

    # Pre-existing edge connecting neighbor to hub
    old_edge = GraphEdge(
        _id="edge_old_eval_hub",
        source_id="neighbor_shared_eval",
        target_id="hub_multi",
        description="General Link",
        project_ids=[project_id],
    )
    db_engine.upsert_edge(old_edge)
    assert len(db_engine.get_edges(project_id)) == 1

    # Split hub into 2 sub-concepts, and rewire the neighbor to BOTH sub_1 and sub_2
    split_cmd_item = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_multi",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Latent Dynamics Sub-Concept",
                "description": "Dynamics modeling.",
                "passage_ids": [],
            },
            {
                "sub_id_alias": "sub_2",
                "title": "Policy Optimization Sub-Concept",
                "description": "Policy learning.",
                "passage_ids": [],
            },
        ],
        "rewired_edges": [
            {
                "neighbor_id": "neighbor_shared_eval",
                "connect_to_sub_alias": "sub_1",
                "relation_type": "EVALUATES",
            },
            {
                "neighbor_id": "neighbor_shared_eval",
                "connect_to_sub_alias": "sub_2",
                "relation_type": "BENCHMARKS",
            },
        ],
    }

    graph_ingestion_engine.execute_single_command(
        item=split_cmd_item, doc_title="Test Doc", proj_list=[project_id]
    )

    all_edges = db_engine.get_edges(project_id)
    # Expected edges:
    # 1. sub_1 -> hub_multi (SUBSET_OF umbrella edge)
    # 2. sub_2 -> hub_multi (SUBSET_OF umbrella edge)
    # 3. neighbor_shared_eval -> sub_1 (EVALUATES)
    # 4. neighbor_shared_eval -> sub_2 (BENCHMARKS)
    # The old edge neighbor_shared_eval -> hub_multi MUST have been deleted!
    assert len(all_edges) == 4

    direct_hub_edges = [
        e
        for e in all_edges
        if (e.source_id == "neighbor_shared_eval" and e.target_id == "hub_multi")
        or (e.source_id == "hub_multi" and e.target_id == "neighbor_shared_eval")
    ]
    assert len(direct_hub_edges) == 0, "Old edge to original hub was not deleted!"

    sub_rewired_edges = [
        e
        for e in all_edges
        if e.source_id == "neighbor_shared_eval" and e.target_id != "hub_multi"
    ]
    assert len(sub_rewired_edges) == 2
    relations = {e.description for e in sub_rewired_edges}
    assert "EVALUATES" in relations
    assert "BENCHMARKS" in relations


def test_split_concept_defensive_guard_prevents_idle_subconcepts():
    """Verify that if LLM omits a sub-concept in rewired_edges, the backend guard

    automatically links the idle sub-concept to an available neighbor.
    """
    project_id = "test_idle_guard_project"

    hub_node = GraphNode(
        _id="hub_idle_test",
        node_type="CONCEPT",
        title="Clustered Concept",
        description="Hub to split with an omitted subconcept.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub_node)

    neighbor_node = GraphNode(
        _id="neighbor_context_node",
        node_type="CONCEPT",
        title="Related Context",
        description="Neighbor context.",
        passage_ids=[],
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(neighbor_node)

    old_edge = GraphEdge(
        _id="edge_old_context_hub",
        source_id="neighbor_context_node",
        target_id="hub_idle_test",
        description="General Link",
        project_ids=[project_id],
    )
    db_engine.upsert_edge(old_edge)

    # Split into 2 sub-concepts, but the rewired_edges ONLY mentions sub_1!
    split_cmd_item = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_idle_test",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Sub 1 Active",
                "description": "Active sub-concept",
                "passage_ids": [],
            },
            {
                "sub_id_alias": "sub_2",
                "title": "Sub 2 Forgotten",
                "description": "Omitted by LLM in rewired_edges",
                "passage_ids": [],
            },
        ],
        "rewired_edges": [
            {
                "neighbor_id": "neighbor_context_node",
                "connect_to_sub_alias": "sub_1",
                "relation_type": "RELEVANT_TO",
            }
        ],
    }

    graph_ingestion_engine.execute_single_command(
        item=split_cmd_item, doc_title="Test Doc", proj_list=[project_id]
    )

    all_edges = db_engine.get_edges(project_id)
    # Expected edges:
    # 1. sub_1 -> hub (SUBSET_OF)
    # 2. sub_2 -> hub (SUBSET_OF)
    # 3. neighbor -> sub_1 (explicitly rewired)
    # 4. neighbor -> sub_2 (auto-fallback connected so sub_2 is NOT idle!)
    assert len(all_edges) == 4

    sub_rewired_edges = [
        e
        for e in all_edges
        if e.source_id == "neighbor_context_node" and e.target_id != "hub_idle_test"
    ]
    assert len(sub_rewired_edges) == 2, "Defensive guard failed to connect sub_2!"
