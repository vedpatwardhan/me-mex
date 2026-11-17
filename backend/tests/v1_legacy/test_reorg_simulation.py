"""Discrete-event sanity checks for v0.2 lateral vs wrapper reorganization."""

import pytest
from app.db import db_engine
from app.models import GraphNode, GraphEdge
from app.services.graph_analytics import MutableTreeIndex
from app.services.graph_ingestion_engine import graph_ingestion_engine

pytestmark = pytest.mark.xdist_group(name="worker1")


def test_wrapper_split_mints_departments_under_genesis():
    proj = ["proj_sim_wrapper"]
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="Genesis",
        project_ids=proj,
        metadata={"immutable": False, "is_genesis": True},
    )
    db_engine.upsert_node(genesis)
    imm_ids = []
    for i in range(7):
        cid = f"imm_sim_{i}"
        imm_ids.append(cid)
        db_engine.upsert_node(
            GraphNode(
                _id=cid,
                node_type="CONCEPT",
                title=f"Topic {i}",
                project_ids=proj,
                metadata={"immutable": True},
            )
        )
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{cid}_g",
                source_id=cid,
                target_id=genesis.id,
                description="RELEVANT_TO",
                project_ids=proj,
            )
        )

    cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": genesis.id,
        "parent_title": "Everything",
        "parent_description": "Updated genesis scope",
        "sub_concepts": [
            {"sub_id_alias": "s1", "title": "Dept A", "description": "Cluster A"},
            {"sub_id_alias": "s2", "title": "Dept B", "description": "Cluster B"},
        ],
        "rewired_edges": [
            {"neighbor_id": imm_ids[i], "connect_to_sub_alias": "s1" if i < 4 else "s2"}
            for i in range(7)
        ],
    }
    evt = graph_ingestion_engine.execute_single_command(cmd, "sim", proj)
    tree = MutableTreeIndex(project_id=proj[0])
    depts = tree.mutable_children(genesis.id)
    assert len(depts) >= 2
    rewire_events = evt.get("rewire_events") or []
    assert len(rewire_events) == 7
    assert all(e["event"] == "reorg_neighbor_rewired" for e in rewire_events)
    kinds = {e["target_kind"] for e in rewire_events}
    assert kinds == {"sub_concept"}


def _genesis_wrapper_children(project_id: str, genesis_id: str) -> list:
    return [
        n
        for n in db_engine.get_nodes(project_id)
        if n.metadata.get("split_under_genesis") == genesis_id
    ]


def test_wrapper_split_skips_unassigned_sub_concepts():
    proj = ["proj_sim_wrapper_lazy"]
    genesis = GraphNode(
        _id="concept_genesis_lazy",
        node_type="CONCEPT",
        title="Everything",
        description="Genesis",
        project_ids=proj,
        metadata={"immutable": False, "is_genesis": True},
    )
    db_engine.upsert_node(genesis)
    imm_ids = []
    for i in range(4):
        cid = f"imm_lazy_{i}"
        imm_ids.append(cid)
        db_engine.upsert_node(
            GraphNode(
                _id=cid,
                node_type="CONCEPT",
                title=f"Topic {i}",
                project_ids=proj,
                metadata={"immutable": True},
            )
        )
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{cid}_g",
                source_id=cid,
                target_id=genesis.id,
                description="RELEVANT_TO",
                project_ids=proj,
            )
        )

    cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": genesis.id,
        "parent_title": "Everything",
        "parent_description": "Updated genesis scope",
        "sub_concepts": [
            {"sub_id_alias": "s1", "title": "Dept A", "description": "Cluster A"},
            {"sub_id_alias": "s2", "title": "Dept B", "description": "Unused cluster"},
        ],
        "rewired_edges": [
            {"neighbor_id": imm_id, "connect_to_sub_alias": "s1"} for imm_id in imm_ids
        ],
    }
    graph_ingestion_engine.execute_single_command(cmd, "sim", proj)
    wrappers = _genesis_wrapper_children(proj[0], genesis.id)
    assert len(wrappers) == 1
    assert wrappers[0].title == "Dept A"


def test_wrapper_split_all_everything_mints_none():
    proj = ["proj_sim_wrapper_everything"]
    genesis = GraphNode(
        _id="concept_genesis_ev",
        node_type="CONCEPT",
        title="Everything",
        description="Genesis",
        project_ids=proj,
        metadata={"immutable": False, "is_genesis": True},
    )
    db_engine.upsert_node(genesis)
    imm_ids = []
    for i in range(3):
        cid = f"imm_ev_{i}"
        imm_ids.append(cid)
        db_engine.upsert_node(
            GraphNode(
                _id=cid,
                node_type="CONCEPT",
                title=f"Topic {i}",
                project_ids=proj,
                metadata={"immutable": True},
            )
        )
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{cid}_g",
                source_id=cid,
                target_id=genesis.id,
                description="RELEVANT_TO",
                project_ids=proj,
            )
        )

    cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": genesis.id,
        "parent_title": "Everything",
        "parent_description": "No new departments",
        "sub_concepts": [
            {"sub_id_alias": "s1", "title": "Unused A", "description": "A"},
            {"sub_id_alias": "s2", "title": "Unused B", "description": "B"},
        ],
        "rewired_edges": [
            {"neighbor_id": imm_id, "connect_to_sub_alias": "EVERYTHING"}
            for imm_id in imm_ids
        ],
    }
    graph_ingestion_engine.execute_single_command(cmd, "sim", proj)
    assert len(_genesis_wrapper_children(proj[0], genesis.id)) == 0


def test_lateral_split_keeps_immutable_depth_invariant():
    proj = ["proj_sim_lateral"]
    genesis = GraphNode(
        _id="g_lat",
        title="Everything",
        project_ids=proj,
        metadata={"immutable": False, "is_genesis": True},
    )
    parent = GraphNode(
        _id="p_lat",
        title="Parent",
        project_ids=proj,
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="h_lat",
        title="Overflow",
        project_ids=proj,
        metadata={"immutable": False},
    )
    leaves = []
    for i in range(7):
        lid = f"leaf_lat_{i}"
        leaves.append(lid)
        db_engine.upsert_node(
            GraphNode(
                _id=lid,
                title=f"Leaf {i}",
                project_ids=proj,
                metadata={"immutable": True},
            )
        )
    for n in [genesis, parent, hub]:
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_pl",
            source_id="p_lat",
            target_id="g_lat",
            description="SUBSET_OF",
            project_ids=proj,
        )
    )
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_hl",
            source_id="h_lat",
            target_id="p_lat",
            description="SUBSET_OF",
            project_ids=proj,
        )
    )
    for lid in leaves:
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{lid}_h",
                source_id=lid,
                target_id="h_lat",
                description="RELEVANT_TO",
                project_ids=proj,
            )
        )

    tree_before = MutableTreeIndex(project_id=proj[0])
    depth_before = tree_before.tree_depth_from_genesis.get("p_lat", 0)

    cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "h_lat",
        "parent_title": "Overflow A",
        "parent_description": "Split half",
        "sub_concepts": [
            {"sub_id_alias": "a", "title": "Hub A", "description": "A"},
            {"sub_id_alias": "b", "title": "Hub B", "description": "B"},
        ],
        "rewired_edges": [
            {"neighbor_id": leaves[i], "connect_to_sub_alias": "a" if i < 4 else "b"}
            for i in range(7)
        ],
    }
    evt = graph_ingestion_engine.execute_single_command(cmd, "sim", proj)
    tree_after = MutableTreeIndex(project_id=proj[0])
    assert tree_after.parent_of("h_lat") == "p_lat"
    assert depth_before == tree_after.tree_depth_from_genesis.get("p_lat", 0)
    assert evt.get("reorg_strategy") == "replacement"


def test_replacement_split_ancestor_leftover_no_link_class():
    proj = ["proj_sim_ancestor"]
    parent = GraphNode(
        _id="p_anc",
        title="Parent Hub",
        project_ids=proj,
        metadata={"immutable": False},
    )
    hub = GraphNode(
        _id="h_anc",
        title="Hot Hub",
        project_ids=proj,
        metadata={"immutable": False},
    )
    grouped = GraphNode(
        _id="imm_g",
        title="Grouped",
        project_ids=proj,
        metadata={"immutable": True},
    )
    leftover = GraphNode(
        _id="imm_l",
        title="Leftover",
        project_ids=proj,
        metadata={"immutable": True},
    )
    for n in [parent, hub, grouped, leftover]:
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_hp",
            source_id="h_anc",
            target_id="p_anc",
            description="SUBSET_OF",
            project_ids=proj,
        )
    )
    for imm, eid in [(grouped, "e_g"), (leftover, "e_l")]:
        db_engine.upsert_edge(
            GraphEdge(
                _id=eid,
                source_id=imm.id,
                target_id="h_anc",
                description="RELEVANT_TO",
                project_ids=proj,
            )
        )

    cmd = {
        "action": "SPLIT_CONCEPT",
        "concept_id": "h_anc",
        "parent_title": "Hot Hub A",
        "parent_description": "First sibling",
        "sub_concepts": [
            {"sub_id_alias": "a", "title": "Hot Hub A", "description": "A"},
            {"sub_id_alias": "b", "title": "Hot Hub B", "description": "B"},
        ],
        "rewired_edges": [
            {"neighbor_id": "imm_g", "connect_to_sub_alias": "a"},
            {"neighbor_id": "imm_l", "connect_to_sub_alias": "ANCESTOR"},
        ],
    }
    evt = graph_ingestion_engine.execute_single_command(cmd, "sim", proj)
    assert evt.get("ungrouped_to_ancestor_count") == 1
    rewire_events = evt.get("rewire_events") or []
    by_source = {e["source_id"]: e for e in rewire_events}
    assert by_source["imm_l"]["target_kind"] == "ancestor"
    assert by_source["imm_l"]["target_id"] == "p_anc"
    assert by_source["imm_g"]["target_kind"] == "sub_concept"
    edges = db_engine.get_edges(proj[0])
    leftover_targets = [
        e.target_id
        for e in edges
        if e.source_id == "imm_l" and e.description == "RELEVANT_TO"
    ]
    assert leftover_targets == ["p_anc"]
    for e in edges:
        assert "link_class" not in (e.metadata or {})
