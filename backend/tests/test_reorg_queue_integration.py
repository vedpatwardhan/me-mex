"""Integration: unified queue defers parent until discover siblings finish."""

from unittest.mock import MagicMock

from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.reorg_queue import ReorgQueue, ReorgWorkItem


def test_process_reorg_queue_defers_parent_until_siblings_done(monkeypatch):
    project_id = "test_reorg_queue_integration"
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
    build_order: list[str] = []
    execution_order: list[str] = []

    def fake_build(hub_id, project_id=project_id, emitted_events=None):
        build_order.append(hub_id)
        return {
            "action": "SPLIT_CONCEPT",
            "concept_id": hub_id,
            "sub_concepts": [{"sub_id_alias": "s1", "title": "S", "description": ""}],
            "rewired_edges": [],
            "partition_neighbor_ids": [],
        }

    def fake_execute(cmd, doc_title, proj_list):
        execution_order.append(cmd["concept_id"])
        return {"event": "reorg_completed", "node_id": cmd["concept_id"]}

    mock_engine = MagicMock()
    mock_engine.execute_single_command.side_effect = fake_execute

    monkeypatch.setattr(agent, "build_split_command_for_hub", fake_build)
    from app.services.graph_analytics import MutableTreeIndex

    monkeypatch.setattr(MutableTreeIndex, "effective_degree", lambda self, node_id: 999)

    q = ReorgQueue()
    q.enqueue_discover_fifo(
        ReorgWorkItem("child1", "discover", "parent_hub"),
    )
    q.enqueue_discover_fifo(
        ReorgWorkItem("child2", "discover", "parent_hub"),
    )

    events: list = []
    agent._process_reorg_queue(
        q,
        project_id=project_id,
        degree_threshold=7,
        doc_title="t",
        proj_list=[project_id],
        ingestion_engine=mock_engine,
        emitted_events=events,
        plan_only=False,
        node_map={n.id: n for n in (c1, c2, parent, genesis)},
    )

    assert build_order.index("child1") < build_order.index("child2")
    assert build_order.index("child2") < build_order.index("parent_hub")
    assert execution_order.index("child1") < execution_order.index("child2")
    assert execution_order.index("child2") < execution_order.index("parent_hub")


def test_build_split_at_pop_not_before_prior_execute(monkeypatch):
    """Hub2 split is planned only after hub1 execute (lazy dequeue build)."""
    project_id = "test_lazy_build_order"
    agent = GraphNavigator(project_id=project_id)
    build_order: list[str] = []
    execute_order: list[str] = []

    def fake_build(hub_id, project_id=project_id, emitted_events=None):
        build_order.append(hub_id)
        return {
            "action": "SPLIT_CONCEPT",
            "concept_id": hub_id,
            "sub_concepts": [{"sub_id_alias": "s1", "title": "S", "description": ""}],
            "rewired_edges": [],
            "partition_neighbor_ids": [],
        }

    mock_engine = MagicMock()
    mock_engine.execute_single_command.side_effect = lambda cmd, *_: (
        execute_order.append(cmd["concept_id"]) or {"event": "reorg_completed"}
    )

    monkeypatch.setattr(agent, "build_split_command_for_hub", fake_build)

    q = ReorgQueue()
    q.enqueue_discover_fifo(ReorgWorkItem("hub1", "discover", "P"))
    q.enqueue_discover_fifo(ReorgWorkItem("hub2", "discover", "P"))

    agent._process_reorg_queue(
        q,
        project_id=project_id,
        degree_threshold=999,
        doc_title="t",
        proj_list=[project_id],
        ingestion_engine=mock_engine,
        emitted_events=[],
        plan_only=False,
        node_map={},
    )

    assert build_order[0] == "hub1"
    assert execute_order[0] == "hub1"
    assert build_order[1] == "hub2"
    assert execute_order.index("hub1") < build_order.index("hub2")
