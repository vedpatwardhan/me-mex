import time
from app.agents.orchestrator import orchestrator
from app.agents.department_persona import DepartmentPersonaAgent
from app.models import GraphNode, GraphEdge
from app.db import db_engine


def test_reconciliation_no_conflict():
    """Verify Path 1 (No Conflict): Non-conflicting persona proposals update existing node directly."""
    # Setup test concept node in DB
    existing_id = "concept_test_no_conflict"
    test_node = GraphNode(
        _id=existing_id,
        node_type="concept",
        title="Test Concept Node",
        description="# Test Concept Node\nInitial body text.",
        passage_ids=["pass_01"],
        project_ids=["global"],
        metadata={"status": "PRIMARY_ACTIVE"},
    )
    db_engine.upsert_node(test_node)

    hub_node = GraphNode(
        _id="hub_test_1",
        node_type="concept",
        title="Domain Hub 1",
        description="# Domain Hub 1",
        passage_ids=[],
        project_ids=["global"],
        metadata={"status": "PRIMARY_ACTIVE"},
    )
    db_engine.upsert_node(hub_node)
    persona = DepartmentPersonaAgent(hub_node)

    consolidated_concepts = [
        {
            "title": "Test Concept Node",
            "description": "New insight",
            "passage_ids": ["pass_02"],
        }
    ]

    persona_command_results = [
        {
            "dept": persona,
            "commands": [
                {
                    "command_type": "EDIT_CONCEPT",
                    "concept": {
                        "id": existing_id,
                        "title": "Test Concept Node",
                        "description": "Non-conflicting insight.",
                        "passage_ids": ["pass_02"],
                    },
                }
            ],
        }
    ]

    concept_idx_to_node = {}
    list(
        orchestrator._create_intra_document_subgraph(
            doc_id="doc_test_1",
            doc_title="Test Doc 1",
            doc_description="Doc Description 1",
            doc_type="paper",
            consolidated_concepts=consolidated_concepts,
            consolidated_relations=[],
            project_id="global",
            proj_list=["global"],
            passage_ids=["pass_01", "pass_02"],
            concept_idx_to_node=concept_idx_to_node,
        )
    )

    events = list(
        orchestrator._apply_ingestion_graph_updates(
            doc_id="doc_test_1",
            doc_title="Test Doc 1",
            doc_description="Doc Description 1",
            doc_type="paper",
            consolidated_concepts=consolidated_concepts,
            consolidated_relations=[],
            persona_command_results=persona_command_results,
            project_id="global",
            proj_list=["global"],
            passage_ids=["pass_01", "pass_02"],
            concept_idx_to_node=concept_idx_to_node,
        )
    )

    updated_node = db_engine.get_node(existing_id)
    assert updated_node is not None
    assert "Non-conflicting insight." in updated_node.description
    assert "pass_02" in updated_node.passage_ids


def test_reconciliation_conflict_debate():
    """Verify Path 2 (Conflict): Conflicting proposals trigger Multi-Persona Debate turn."""
    target_a = "concept_target_a"
    target_b = "concept_target_b"

    node_a = GraphNode(
        _id=target_a,
        node_type="concept",
        title="Domain A Node",
        description="Body A",
        passage_ids=[],
        project_ids=["global"],
    )
    node_b = GraphNode(
        _id=target_b,
        node_type="concept",
        title="Domain B Node",
        description="Body B",
        passage_ids=[],
        project_ids=["global"],
    )
    db_engine.upsert_node(node_a)
    db_engine.upsert_node(node_b)

    persona_a = DepartmentPersonaAgent(node_a)
    persona_b = DepartmentPersonaAgent(node_b)

    consolidated_concepts = [
        {
            "title": "Cross Domain Concept",
            "description": "Overlapping topic across A and B",
            "passage_ids": ["pass_03"],
        }
    ]

    persona_command_results = [
        {
            "dept": persona_a,
            "commands": [
                {
                    "command_type": "EDIT_CONCEPT",
                    "concept": {
                        "id": target_a,
                        "title": "Domain A Node",
                        "description": "Merge to A",
                    },
                }
            ],
        },
        {
            "dept": persona_b,
            "commands": [
                {
                    "command_type": "EDIT_CONCEPT",
                    "concept": {
                        "id": target_b,
                        "title": "Domain B Node",
                        "description": "Merge to B",
                    },
                }
            ],
        },
    ]

    original_debate = orchestrator._run_multi_persona_debate

    def mock_debate(*args, **kwargs):
        return {
            "resolution_type": "SUBDIVIDE",
            "rationale": "Concept spans both domains; sub-dividing.",
            "sub_concepts": [
                {
                    "sub_title": "Cross Domain Concept (Domain A)",
                    "description": "Part A",
                    "target_node_id": target_a,
                    "passage_ids": ["pass_03"],
                },
                {
                    "sub_title": "Cross Domain Concept (Domain B)",
                    "description": "Part B",
                    "target_node_id": target_b,
                    "passage_ids": ["pass_03"],
                },
            ],
            "additional_edges": [
                {
                    "source_ref": target_a,
                    "target_ref": target_b,
                    "description": "Bridge between domain A and domain B",
                }
            ],
        }

    orchestrator._run_multi_persona_debate = mock_debate

    try:
        concept_idx_to_node = {}
        list(
            orchestrator._create_intra_document_subgraph(
                doc_id="doc_test_2",
                doc_title="Test Doc 2",
                doc_description="Doc Description 2",
                doc_type="paper",
                consolidated_concepts=consolidated_concepts,
                consolidated_relations=[],
                project_id="global",
                proj_list=["global"],
                passage_ids=["pass_03"],
                concept_idx_to_node=concept_idx_to_node,
            )
        )
        events = list(
            orchestrator._apply_ingestion_graph_updates(
                doc_id="doc_test_2",
                doc_title="Test Doc 2",
                doc_description="Doc Description 2",
                doc_type="paper",
                consolidated_concepts=consolidated_concepts,
                consolidated_relations=[],
                persona_command_results=persona_command_results,
                project_id="global",
                proj_list=["global"],
                passage_ids=["pass_03"],
                concept_idx_to_node=concept_idx_to_node,
            )
        )
    finally:
        orchestrator._run_multi_persona_debate = original_debate

    event_types = [e.get("event") for e in events]
    assert "persona_debate_start" in event_types
    assert "persona_debate_complete" in event_types

    # Check updated node bodies
    updated_a = db_engine.get_node(target_a)
    updated_b = db_engine.get_node(target_b)
    assert "Sub-concept from 'Test Doc 2'" in updated_a.description
    assert "Sub-concept from 'Test Doc 2'" in updated_b.description


def test_create_and_delete_commands():
    """Verify CREATE_CONCEPT, DELETE_CONCEPT, and DELETE_EDGE commands."""
    node_to_delete = GraphNode(
        _id="concept_obsolete_del",
        node_type="concept",
        title="Obsolete Concept",
        description="To be deleted",
    )
    edge_to_delete = GraphEdge(
        _id="edge_obsolete_del",
        source_id="concept_obsolete_del",
        target_id="hub_test_1",
        description="Obsolete link",
    )
    db_engine.upsert_node(node_to_delete)
    db_engine.upsert_edge(edge_to_delete)

    hub_node = db_engine.get_node("hub_test_1") or GraphNode(
        _id="hub_test_1", node_type="concept", title="Hub Test", description=""
    )
    persona = DepartmentPersonaAgent(hub_node)

    persona_command_results = [
        {
            "dept": persona,
            "commands": [
                {
                    "command_type": "CREATE_CONCEPT",
                    "concept": {
                        "title": "Brand New Persona Concept",
                        "description": "Created directly by specialist persona.",
                        "passage_ids": ["pass_99"],
                    },
                },
                {
                    "command_type": "DELETE_CONCEPT",
                    "concept": {
                        "id": "concept_obsolete_del",
                        "title": "Obsolete Concept",
                    },
                },
                {
                    "command_type": "DELETE_EDGE",
                    "edge": {
                        "id": "edge_obsolete_del",
                    },
                },
            ],
        }
    ]

    list(
        orchestrator._apply_ingestion_graph_updates(
            doc_id="doc_test_cmd",
            doc_title="Test Doc Cmd",
            doc_description="Doc Desc",
            doc_type="paper",
            consolidated_concepts=[],
            consolidated_relations=[],
            persona_command_results=persona_command_results,
            project_id="global",
            proj_list=["global"],
            passage_ids=["pass_99"],
        )
    )

    assert db_engine.get_node("concept_obsolete_del") is None
    assert not any(e.id == "edge_obsolete_del" for e in db_engine.get_edges())
