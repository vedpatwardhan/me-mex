import pytest

from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.agents.orchestrator import orchestrator


@pytest.mark.asyncio
@pytest.mark.vllm
async def test_generalize_affected_target_nodes():
    """Live vLLM: generalization broadens mutable targets; Everything title is preserved."""
    project_id = "proj_test_generalize_pass"

    normal_target = GraphNode(
        _id="concept_target_normal",
        node_type="CONCEPT",
        title="Predictive Models",
        description="Specific models predicting trajectory states.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    everything_target = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Primordial knowledge anchor.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    new_child_1 = GraphNode(
        _id="concept_new_child_1",
        node_type="CONCEPT",
        title="Multimodal Diffusion",
        description="Diffusion models for video generation.",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    new_child_2 = GraphNode(
        _id="concept_new_child_2",
        node_type="CONCEPT",
        title="Quantum Computing Notes",
        description="Foundational principles of quantum states.",
        project_ids=[project_id],
        metadata={"immutable": True},
    )

    db_engine.upsert_node(normal_target)
    db_engine.upsert_node(everything_target)
    db_engine.upsert_node(new_child_1)
    db_engine.upsert_node(new_child_2)

    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_1",
            source_id="concept_new_child_1",
            target_id="concept_target_normal",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="edge_2",
            source_id="concept_new_child_2",
            target_id="concept_genesis",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )

    events = []
    async for evt in orchestrator._generalize_affected_target_nodes(
        mutable_targets=[normal_target, everything_target],
        project_id=project_id,
    ):
        events.append(evt)

    updated_normal = db_engine.get_node("concept_target_normal")
    assert updated_normal.title != "Predictive Models"
    assert len(updated_normal.description) > len(normal_target.description)

    updated_everything = db_engine.get_node("concept_genesis")
    assert updated_everything.title == "Everything"
    assert updated_everything.description != everything_target.description

    assert len(events) >= 1
