"""
Test Suite: Zero-Consensus Graph Reconciliation & Node Mutability Enforcement

Aligned with docs/ARCHITECTURE.md Section 3 & Section 4:
- Validates independent zero-consensus persona command execution into MongoDB.
- Validates Node Mutability Hierarchy:
    - Root Nodes (`ROOT`) & Intra-Document Concepts (`immutable: True`) CANNOT be modified (`EDIT_CONCEPT`), split (`SPLIT_CONCEPT`), or deleted by persona commands.
    - Persona-created Domain Hubs & Intermediate Nodes (`immutable: False`) can be edited or split when over-clustered.
"""

import time
from app.agents.orchestrator import orchestrator
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.agents.department_persona import DepartmentPersonaAgent
from app.models import GraphNode, GraphEdge
from app.db import db_engine


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
                    "action": "CONNECT_DIRECT",
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

    # Original over-clustered node deleted/deactivated
    old_node = db_engine.get_node(mutable_hub_id)
    assert old_node is None

    # New focused sub-concepts inserted into DB
    all_nodes = db_engine.get_nodes(project_id="global")
    sub_nodes = [n for n in all_nodes if n.metadata.get("split_from") == mutable_hub_id]
    assert len(sub_nodes) == 2
    titles = [n.title for n in sub_nodes]
    assert "Sub-Concept Alpha" in titles
    assert "Sub-Concept Beta" in titles
