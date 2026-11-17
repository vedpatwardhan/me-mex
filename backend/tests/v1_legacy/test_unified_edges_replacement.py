"""Unified edges + replacement split upward severance (v0.2.6)."""

import pytest

from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.graph_analytics import MutableTreeIndex, graph_analytics
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.services.graph_link_utils import MUTABLE_PARENT_META_KEY


@pytest.fixture
def project_id():
    return "test_unified_edges_replacement"


def test_replacement_split_severs_then_rehangs_subs(project_id):
    genesis = GraphNode(
        _id="gen_u",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"immutable": False, "is_genesis": True},
    )
    parent = GraphNode(
        _id="parent_u",
        node_type="CONCEPT",
        title="Parent",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="hub_u",
        node_type="CONCEPT",
        title="Old Umbrella",
        project_ids=[project_id],
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "parent_u"},
    )
    n1 = GraphNode(
        _id="imm_u1",
        node_type="CONCEPT",
        title="E1",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    n2 = GraphNode(
        _id="imm_u2",
        node_type="CONCEPT",
        title="E2",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for node in (genesis, parent, hub, n1, n2):
        db_engine.upsert_node(node)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_p_g",
            source_id="parent_u",
            target_id="gen_u",
            description="",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_h_p",
            source_id="hub_u",
            target_id="parent_u",
            description="",
            project_ids=[project_id],
        )
    )
    for nid in ("imm_u1", "imm_u2"):
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{nid}",
                source_id=nid,
                target_id="hub_u",
                description="",
                project_ids=[project_id],
            )
        )

    split_cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "hub_u",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Focused Sub",
                "description": "Focused scope",
            }
        ],
        "rewired_edges": [
            {"neighbor_id": "imm_u1", "connect_to_sub_alias": "sub_1"},
        ],
        "partition_neighbor_ids": ["imm_u1", "imm_u2"],
    }
    graph_ingestion_engine.execute_single_command(
        split_cmd, doc_title="Doc", proj_list=[project_id]
    )

    hub_node = db_engine.get_node("hub_u")
    assert hub_node.title == "Focused Sub"
    assert hub_node.metadata.get(MUTABLE_PARENT_META_KEY) == "parent_u"

    tree = MutableTreeIndex(project_id=project_id)
    assert tree.parent_of("hub_u") == "parent_u"

    neighbor_ids = {
        e["id"]
        for e in GraphNavigator._neighbor_entries_for_hub("parent_u", project_id, tree)
    }
    assert "hub_u" in neighbor_ids


def test_genesis_partition_includes_mutable_direct_neighbor(project_id):
    genesis = GraphNode(
        _id="gen_c",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"immutable": False, "is_genesis": True},
    )
    child = GraphNode(
        _id="child_c",
        node_type="CONCEPT",
        title="Child Hub",
        project_ids=[project_id],
        metadata={"immutable": False, MUTABLE_PARENT_META_KEY: "gen_c"},
    )
    imm = GraphNode(
        _id="imm_c",
        node_type="CONCEPT",
        title="Evidence",
        project_ids=[project_id],
        metadata={"immutable": True},
    )
    for n in (genesis, child, imm):
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_c_g",
            source_id="child_c",
            target_id="gen_c",
            description="",
            project_ids=[project_id],
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_i_g",
            source_id="imm_c",
            target_id="gen_c",
            description="linked to genesis",
            project_ids=[project_id],
        )
    )
    tree = MutableTreeIndex(project_id=project_id)
    ids = {
        e["id"]
        for e in GraphNavigator._neighbor_entries_for_hub("gen_c", project_id, tree)
    }
    assert "child_c" in ids
    assert "imm_c" in ids


def test_merge_partition_no_legacy_edge_type_keys():
    from app.services.reorg_rewire_utils import merge_partition_to_engine_rewires

    merged = merge_partition_to_engine_rewires(
        [{"neighbor_index": 1, "connect_to_sub_alias": "sub_1", "description": "a"}],
        [{"neighbor_index": 2, "rationale": "overflow"}],
        "ANCESTOR",
    )
    for row in merged:
        assert "relation_type" not in row
        assert "edge_description" not in row
        assert "relation_desc" not in row
