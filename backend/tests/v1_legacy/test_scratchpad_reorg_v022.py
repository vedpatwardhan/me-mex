"""Tests for scratchpad-aligned reorg v0.2.2 (closure, queue, partition scope)."""

import pytest

from app.agents.graph_navigator import GraphNavigator
from app.services.reorg_queue import cascade_parent_id
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.services.reorg_rewire_utils import finalize_rewire_edges
from app.services.graph_link_utils import MUTABLE_PARENT_META_KEY


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
    hub.metadata[MUTABLE_PARENT_META_KEY] = "parent_p"
    db_engine.upsert_node(parent)
    db_engine.upsert_node(hub)
    db_engine.upsert_edge(
        GraphEdge(
            _id="sub",
            source_id="hub_stale",
            target_id="parent_p",
            description="",
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
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "concept_genesis"},
    )
    db_engine.upsert_node(genesis)
    db_engine.upsert_node(child)
    db_engine.upsert_edge(
        GraphEdge(
            _id="c_g",
            source_id="child_hub",
            target_id="concept_genesis",
            description="",
            project_ids=[project_id],
        )
    )
    tree = MutableTreeIndex(project_id=project_id)
    pid = cascade_parent_id(tree, "child_hub", child)
    assert pid == "concept_genesis"
    pid_gen = cascade_parent_id(tree, "concept_genesis", genesis)
    assert pid_gen is None


def test_reorg_queue_filo_prepends_cascade_before_next_discover():
    """Simulate queue: after processing hub A, cascade parent P is prepended before hub B."""
    from app.services.reorg_queue import ReorgQueue, ReorgWorkItem

    q = ReorgQueue()
    q.enqueue_discover_fifo(ReorgWorkItem("A", "discover", "P"))
    q.enqueue_discover_fifo(ReorgWorkItem("B", "discover", "P"))
    q.prepend_cascade_filo(ReorgWorkItem("P_cascade", "cascade", None))
    order = [q.pop_front().hub_id for _ in range(3)]
    assert order == ["P_cascade", "A", "B"]


def test_genesis_wrapper_reuses_existing_mutable_child(project_id):
    """Immutables rewire to existing mutable child; no duplicate hub minted."""
    genesis = GraphNode(
        _id="genesis_reuse",
        node_type="CONCEPT",
        title="Everything",
        description="Root",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    existing_child = GraphNode(
        _id="mut_existing_hub",
        node_type="CONCEPT",
        title="Existing Department Hub",
        description="Already under Genesis",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    imm_a = GraphNode(
        _id="imm_reuse_a",
        node_type="CONCEPT",
        title="Evidence A",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    imm_b = GraphNode(
        _id="imm_reuse_b",
        node_type="CONCEPT",
        title="Evidence B",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for n in (genesis, existing_child, imm_a, imm_b):
        db_engine.upsert_node(n)
    from app.services.graph_link_utils import set_mutable_parent

    set_mutable_parent(
        existing_child.id, genesis.id, [project_id], project_scope=project_id
    )
    for imm_id in ("imm_reuse_a", "imm_reuse_b"):
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{imm_id}_g",
                source_id=imm_id,
                target_id=genesis.id,
                description="linked",
                project_ids=[project_id],
            )
        )

    nodes_before = len(db_engine.get_nodes(project_id))
    split_cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": genesis.id,
        "parent_title": "Everything",
        "parent_description": "Root",
        "sub_concepts": [],
        "rewired_edges": [
            {
                "neighbor_id": "imm_reuse_a",
                "connect_to_sub_alias": "",
                "connect_to_target_id": "mut_existing_hub",
            },
            {
                "neighbor_id": "imm_reuse_b",
                "connect_to_sub_alias": "",
                "connect_to_target_id": "mut_existing_hub",
            },
        ],
        "partition_neighbor_ids": [
            "mut_existing_hub",
            "imm_reuse_a",
            "imm_reuse_b",
        ],
    }
    graph_ingestion_engine.execute_single_command(
        split_cmd, doc_title="Doc", proj_list=[project_id]
    )
    nodes_after = len(db_engine.get_nodes(project_id))
    assert nodes_after == nodes_before

    child = db_engine.get_node("mut_existing_hub")
    assert child.metadata.get(MUTABLE_PARENT_META_KEY) == genesis.id
    for imm_id in ("imm_reuse_a", "imm_reuse_b"):
        edges = [
            e
            for e in db_engine.get_edges(project_id)
            if e.source_id == imm_id and e.target_id == "mut_existing_hub"
        ]
        assert len(edges) == 1
    to_genesis = [
        e
        for e in db_engine.get_edges(project_id)
        if e.source_id in ("imm_reuse_a", "imm_reuse_b") and e.target_id == genesis.id
    ]
    assert to_genesis == []


def test_genesis_wrapper_reparents_mutable_neighbors(project_id):
    """Mutable direct neighbors in partition batch move under new wrapper with parent metadata."""
    from app.services.graph_analytics import MutableTreeIndex

    genesis = GraphNode(
        _id="genesis_sc",
        node_type="CONCEPT",
        title="Everything",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False, "is_genesis": True},
    )
    m1 = GraphNode(
        _id="mut_child_a",
        node_type="CONCEPT",
        title="Mutable A",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "genesis_sc"},
    )
    m2 = GraphNode(
        _id="mut_child_b",
        node_type="CONCEPT",
        title="Mutable B",
        description="",
        project_ids=[project_id],
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "genesis_sc"},
    )
    imm = GraphNode(
        _id="imm_orphan",
        node_type="CONCEPT",
        title="Evidence",
        description="",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for node in (genesis, m1, m2, imm):
        db_engine.upsert_node(node)
    for src in ("mut_child_a", "mut_child_b", "imm_orphan"):
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{src}_g",
                source_id=src,
                target_id="genesis_sc",
                description="",
                project_ids=[project_id],
            )
        )

    tree = MutableTreeIndex(project_id=project_id)
    batch_ids = {
        e["id"]
        for e in GraphNavigator._neighbor_entries_for_hub(
            "genesis_sc", project_id, tree
        )
    }
    assert batch_ids == {"mut_child_a", "mut_child_b", "imm_orphan"}

    split_cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "genesis_sc",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Grouped Mutables",
                "description": "Sub hub",
            }
        ],
        "rewired_edges": [
            {"neighbor_id": "mut_child_a", "connect_to_sub_alias": "sub_1"},
            {"neighbor_id": "mut_child_b", "connect_to_sub_alias": "sub_1"},
            {"neighbor_id": "imm_orphan", "connect_to_sub_alias": "EVERYTHING"},
        ],
        "partition_neighbor_ids": ["mut_child_a", "mut_child_b", "imm_orphan"],
    }
    graph_ingestion_engine.execute_single_command(
        split_cmd, doc_title="Doc", proj_list=[project_id]
    )

    tree = MutableTreeIndex(project_id=project_id)
    wrapper_children = tree.mutable_children("genesis_sc")
    assert len(wrapper_children) == 1
    wrapper_id = wrapper_children[0].id
    assert tree.parent_of("mut_child_a") == wrapper_id
    assert tree.parent_of("mut_child_b") == wrapper_id
    assert (
        db_engine.get_node("mut_child_a").metadata.get(MUTABLE_PARENT_META_KEY)
        == wrapper_id
    )

    imm_edges = [
        e
        for e in db_engine.get_edges(project_id)
        if e.source_id == "imm_orphan" and e.target_id == "genesis_sc"
    ]
    assert len(imm_edges) == 1
