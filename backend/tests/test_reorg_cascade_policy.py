"""Phase 4 cascade policy: no Genesis self-requeue; split_hubs_this_pass."""

from unittest.mock import MagicMock

from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.reorg_queue import ReorgQueue, ReorgWorkItem


def _setup_genesis_child_chain(project_id: str) -> tuple[GraphNode, GraphNode]:
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    child = GraphNode(
        _id="child_hub",
        node_type="CONCEPT",
        title="Child",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    for n in (genesis, child):
        db_engine.upsert_node(n)
    db_engine.upsert_edge(
        GraphEdge(
            _id="e_child_genesis",
            source_id="child_hub",
            target_id="concept_genesis",
            description="SUBSET_OF",
            project_ids=[project_id],
        )
    )
    return genesis, child


def test_genesis_split_does_not_requeue_genesis(monkeypatch):
    project_id = "test_genesis_no_self_requeue"
    genesis, child = _setup_genesis_child_chain(project_id)
    agent = GraphNavigator(project_id=project_id)
    build_order: list[str] = []

    def fake_build(hub_id, project_id=project_id, emitted_events=None, **kwargs):
        build_order.append(hub_id)
        return {
            "action": "SPLIT_CONCEPT",
            "concept_id": hub_id,
            "sub_concepts": [{"sub_id_alias": "s1", "title": "S", "description": ""}],
            "rewired_edges": [],
            "partition_neighbor_ids": [],
        }

    mock_engine = MagicMock()
    mock_engine.execute_single_command.side_effect = lambda cmd, *_: {
        "event": "reorg_completed",
        "node_id": cmd["concept_id"],
    }

    from app.services.graph_analytics import MutableTreeIndex

    monkeypatch.setattr(agent, "build_split_command_for_hub", fake_build)
    monkeypatch.setattr(MutableTreeIndex, "effective_degree", lambda self, node_id: 999)

    q = ReorgQueue()
    q.enqueue_discover_fifo(ReorgWorkItem("child_hub", "discover", "concept_genesis"))
    q.prepend_cascade_filo(
        ReorgWorkItem("concept_genesis", "cascade", None),
    )

    cascade_events: list = []
    agent._process_reorg_queue(
        q,
        project_id=project_id,
        degree_threshold=7,
        doc_title="t",
        proj_list=[project_id],
        ingestion_engine=mock_engine,
        emitted_events=cascade_events,
        plan_only=False,
        node_map={child.id: child, genesis.id: genesis},
        link_affected_ids=set(),
    )

    assert build_order.count("concept_genesis") == 1
    assert build_order.count("child_hub") == 1
    post_genesis_cascades = [
        e
        for e in cascade_events
        if e.get("event") == "reorg_cascade_iteration"
        and e.get("ancestor_id") == "concept_genesis"
    ]
    assert post_genesis_cascades == []


def test_split_hubs_blocks_second_cascade_to_same_ancestor(monkeypatch):
    project_id = "test_split_hubs_pass_set"
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    parent = GraphNode(
        _id="parent_hub",
        node_type="CONCEPT",
        title="Parent",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    c1 = GraphNode(
        _id="child1",
        node_type="CONCEPT",
        title="Child1",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    c2 = GraphNode(
        _id="child2",
        node_type="CONCEPT",
        title="Child2",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    for n in (genesis, parent, c1, c2):
        db_engine.upsert_node(n)
    for src, tgt in (
        ("parent_hub", "concept_genesis"),
        ("child1", "parent_hub"),
        ("child2", "parent_hub"),
    ):
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"e_{src}_{tgt}",
                source_id=src,
                target_id=tgt,
                description="SUBSET_OF",
                project_ids=[project_id],
            )
        )

    agent = GraphNavigator(project_id=project_id)
    calls: list[str] = []

    def fake_build(hub_id, project_id=project_id, emitted_events=None, **kwargs):
        calls.append(hub_id)
        return {
            "action": "SPLIT_CONCEPT",
            "concept_id": hub_id,
            "sub_concepts": [{"sub_id_alias": "s1", "title": "S", "description": ""}],
            "rewired_edges": [],
            "partition_neighbor_ids": [],
        }

    mock_engine = MagicMock()
    mock_engine.execute_single_command.return_value = {"event": "reorg_completed"}

    from app.services.graph_analytics import MutableTreeIndex

    monkeypatch.setattr(agent, "build_split_command_for_hub", fake_build)
    monkeypatch.setattr(MutableTreeIndex, "effective_degree", lambda self, node_id: 999)

    q = ReorgQueue()
    q.enqueue_discover_fifo(ReorgWorkItem("child1", "discover", "parent_hub"))
    q.enqueue_discover_fifo(ReorgWorkItem("child2", "discover", "parent_hub"))

    agent._process_reorg_queue(
        q,
        project_id=project_id,
        degree_threshold=7,
        doc_title="t",
        proj_list=[project_id],
        ingestion_engine=mock_engine,
        emitted_events=[],
        plan_only=False,
        node_map={n.id: n for n in (c1, c2, parent, genesis)},
    )

    assert calls.count("parent_hub") == 1
    assert calls.index("child1") < calls.index("child2") < calls.index("parent_hub")
