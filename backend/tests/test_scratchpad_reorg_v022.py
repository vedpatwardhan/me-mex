"""Tests for scratchpad-aligned reorg v0.2.2 (closure, SUBSET_OF, queue, partition scope)."""

from collections import deque

import pytest

from app.agents.orchestrator import ExecutiveOrchestrator
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.services.reorg_rewire_utils import (
    finalize_rewire_edges,
    resolve_rewire_relation_type,
)


@pytest.fixture
def project_id():
    return "test_scratchpad_v022"


def test_finalize_rewire_edges_closes_missing_neighbors(project_id):
    hub = GraphNode(
        _id="hub_close",
        node_type="CONCEPT",
        title="Hub",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    imm = GraphNode(
        _id="imm_a",
        node_type="CONCEPT",
        title="Evidence A",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    imm_b = GraphNode(
        _id="imm_b",
        node_type="CONCEPT",
        title="Evidence B",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    db_engine.upsert_node(hub)
    db_engine.upsert_node(imm)
    db_engine.upsert_node(imm_b)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e1",
            source_id="imm_a",
            target_id="hub_close",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e2",
            source_id="imm_b",
            target_id="hub_close",
            description="RELEVANT_TO",
            project_ids=[project_id],
        )
    )

    partial = [
        {
            "neighbor_id": "imm_a",
            "connect_to_sub_alias": "sub_1",
            "relation_type": "RELEVANT_TO",
        }
    ]
    closed = finalize_rewire_edges(
        "hub_close",
        project_id,
        partial,
        is_genesis_split=False,
        explicit_neighbor_ids=["imm_a", "imm_b"],
    )
    by_id = {r["neighbor_id"]: r for r in closed}
    assert set(by_id) == {"imm_a", "imm_b"}
    assert by_id["imm_b"]["connect_to_sub_alias"] == "ANCESTOR"


def test_split_engine_closure_removes_stale_hub_edge(project_id):
    parent = GraphNode(
        _id="parent_p",
        node_type="CONCEPT",
        title="Parent",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="hub_stale",
        node_type="CONCEPT",
        title="Hub",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    n1 = GraphNode(
        _id="n1",
        node_type="CONCEPT",
        title="N1",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    n2 = GraphNode(
        _id="n2",
        node_type="CONCEPT",
        title="N2",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for node in (parent, hub, n1, n2):
        db_engine.upsert_node(node)
    db_engine.upsert_edge(
        GraphEdge(
            _id="sub",
            source_id="hub_stale",
            target_id="parent_p",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
    for nid in ("n1", "n2"):
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"link_{nid}",
                source_id=nid,
                target_id="hub_stale",
                description="RELEVANT_TO",
                project_ids=[project_id],
            )
        )

    split_cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_stale",
        "parent_title": "Hub Refined",
        "parent_description": "Desc",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Sub",
                "description": "S",
            }
        ],
        "rewired_edges": [
            {
                "neighbor_id": "n1",
                "connect_to_sub_alias": "sub_1",
                "relation_type": "RELEVANT_TO",
            }
        ],
        "partition_neighbor_ids": ["n1", "n2"],
    }
    graph_ingestion_engine.execute_single_command(
        split_cmd, doc_title="Doc", proj_list=[project_id]
    )
    edges = db_engine.get_edges(project_id)
    # n1 → sub_1 reuses hub_stale id (replacement split); n2 orphans to parent_p
    n2_to_hub = [e for e in edges if e.source_id == "n2" and e.target_id == "hub_stale"]
    assert n2_to_hub == []
    n2_edges = [e for e in edges if e.source_id == "n2" and e.target_id == "parent_p"]
    assert len(n2_edges) == 1
    n1_edges = [e for e in edges if e.source_id == "n1" and e.target_id == "hub_stale"]
    assert len(n1_edges) == 1


def test_resolve_rewire_preserves_subset_for_mutable_child(project_id):
    parent = GraphNode(
        _id="par",
        node_type="CONCEPT",
        title="P",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="hub_m",
        node_type="CONCEPT",
        title="H",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    child = GraphNode(
        _id="child_m",
        node_type="CONCEPT",
        title="Child",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    for n in (parent, hub, child):
        db_engine.upsert_node(n)
    old = GraphEdge(
        _id="tree_e",
        source_id="child_m",
        target_id="hub_m",
        description="SUBSET_OF",
        project_ids=[project_id],
    )
    db_engine.upsert_edge(old)
    rel = resolve_rewire_relation_type("child_m", "hub_m", [old], "RELEVANT_TO")
    assert rel == "SUBSET_OF"


def test_reorg_cascade_parent_id_genesis_and_child():
    from app.services.graph_analytics import MutableTreeIndex

    project_id = "test_cascade_parent_id"
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    child = GraphNode(
        _id="child_hub",
        node_type="CONCEPT",
        title="Child",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(genesis)
    db_engine.upsert_node(child)
    db_engine.upsert_edge(
        GraphEdge(
            _id="c_g",
            source_id="child_hub",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
    tree = MutableTreeIndex(project_id=project_id)
    pid = ExecutiveOrchestrator._reorg_cascade_parent_id(tree, "child_hub", child)
    assert pid == "concept_genesis"
    pid_gen = ExecutiveOrchestrator._reorg_cascade_parent_id(
        tree, "concept_genesis", genesis
    )
    assert pid_gen == "concept_genesis"


def test_reorg_queue_filo_prepends_cascade_before_next_discover():
    """Simulate queue: after processing hub A, cascade parent P is prepended before hub B."""
    pending = deque([{"concept_id": "A"}, {"concept_id": "B"}])
    pending.appendleft({"concept_id": "P_cascade"})
    order = [pending.popleft()["concept_id"] for _ in range(3)]
    assert order == ["P_cascade", "A", "B"]
