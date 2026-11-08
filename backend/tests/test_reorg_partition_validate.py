"""Validator and merge for three-list reorg partition (v0.2.5)."""

import json

import pytest

from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphEdge, GraphNode
from app.services.reorg_rewire_utils import (
    merge_partition_to_engine_rewires,
    normalize_partition_singleton_subs,
    validate_reorg_partition,
)


def test_validate_accepts_sub_and_overflow_split():
    subs = [
        {"sub_id_alias": "sub_1", "title": "A", "description": "d"},
        {"sub_id_alias": "sub_2", "title": "B", "description": "d"},
    ]
    overflow = [{"neighbor_index": 5, "rationale": "outlier"}]
    edges = [
        {
            "neighbor_index": i,
            "connect_to_sub_alias": "sub_1",
        }
        for i in (1, 2)
    ] + [
        {
            "neighbor_index": i,
            "connect_to_sub_alias": "sub_2",
        }
        for i in (3, 4)
    ]
    ok, errs = validate_reorg_partition(subs, overflow, edges, neighbor_count=5)
    assert ok, errs


def test_validate_rejects_zero_subs():
    ok, errs = validate_reorg_partition([], [], [], neighbor_count=5)
    assert not ok
    assert any("At least one sub_concept" in e for e in errs)


def test_validate_rejects_singleton_sub():
    subs = [{"sub_id_alias": "sub_1", "title": "A", "description": "d"}]
    overflow = [{"neighbor_index": 2, "rationale": "x"}]
    edges = [
        {
            "neighbor_index": 1,
            "connect_to_sub_alias": "sub_1",
        },
    ]
    ok, errs = validate_reorg_partition(subs, overflow, edges, neighbor_count=2)
    assert not ok
    assert any("minimum is 2" in e for e in errs)


def test_validate_rejects_overflow_alias_in_rewired_edges():
    subs = [{"sub_id_alias": "sub_1", "title": "A", "description": "d"}]
    edges = [
        {
            "neighbor_index": 1,
            "connect_to_sub_alias": "sub_1",
        },
        {
            "neighbor_index": 2,
            "connect_to_sub_alias": "sub_1",
        },
        {
            "neighbor_index": 3,
            "connect_to_sub_alias": "ANCESTOR",
        },
    ]
    ok, errs = validate_reorg_partition(subs, [], edges, neighbor_count=3)
    assert not ok
    assert any("overflow alias" in e for e in errs)


def test_validate_rejects_too_many_subs():
    subs = [
        {"sub_id_alias": f"sub_{i}", "title": "t", "description": "d"} for i in range(4)
    ]
    edges = []
    idx = 1
    for s in range(4):
        for _ in range(2):
            edges.append(
                {
                    "neighbor_index": idx,
                    "connect_to_sub_alias": f"sub_{s}",
                }
            )
            idx += 1
    ok, errs = validate_reorg_partition(subs, [], edges, neighbor_count=5)
    assert not ok
    assert any("Too many sub_concepts" in e for e in errs)


def test_normalize_singleton_sub_moves_to_overflow_and_validates():
    """Thin sub_2 with one neighbor is demoted; sub_1 keeps two neighbors."""
    subs = [
        {"sub_id_alias": "sub_1", "title": "A", "description": "d"},
        {"sub_id_alias": "sub_2", "title": "B", "description": "d"},
    ]
    overflow = []
    edges = [
        {"neighbor_index": 1, "connect_to_sub_alias": "sub_1"},
        {"neighbor_index": 2, "connect_to_sub_alias": "sub_1"},
        {"neighbor_index": 3, "connect_to_sub_alias": "sub_2"},
    ]
    subs_n, overflow_n, edges_n, demotions = normalize_partition_singleton_subs(
        subs, overflow, edges
    )
    assert len(demotions) == 1
    assert demotions[0]["sub_id_alias"] == "sub_2"
    assert demotions[0]["neighbor_index"] == 3
    assert len(subs_n) == 1
    assert subs_n[0]["sub_id_alias"] == "sub_1"
    assert len(overflow_n) == 1
    assert overflow_n[0]["neighbor_index"] == 3
    ok, errs = validate_reorg_partition(subs_n, overflow_n, edges_n, neighbor_count=3)
    assert ok, errs


def test_normalize_noop_when_all_subs_have_two_or_more_neighbors():
    subs = [
        {"sub_id_alias": "sub_1", "title": "A", "description": "d"},
        {"sub_id_alias": "sub_2", "title": "B", "description": "d"},
    ]
    overflow = [{"neighbor_index": 5, "rationale": "outlier"}]
    edges = [{"neighbor_index": i, "connect_to_sub_alias": "sub_1"} for i in (1, 2)] + [
        {"neighbor_index": i, "connect_to_sub_alias": "sub_2"} for i in (3, 4)
    ]
    subs_n, overflow_n, edges_n, demotions = normalize_partition_singleton_subs(
        subs, overflow, edges
    )
    assert demotions == []
    assert subs_n == subs
    assert overflow_n == overflow
    assert edges_n == edges


def test_merge_adds_overflow_with_engine_alias():
    sub_edges = [
        {
            "neighbor_index": 1,
            "connect_to_sub_alias": "sub_1",
        },
        {
            "neighbor_index": 2,
            "connect_to_sub_alias": "sub_1",
        },
    ]
    overflow = [{"neighbor_index": 3, "rationale": "orphan"}]
    merged = merge_partition_to_engine_rewires(sub_edges, overflow, "EVERYTHING")
    assert len(merged) == 3
    assert merged[2]["connect_to_sub_alias"] == "EVERYTHING"
    assert merged[2]["neighbor_index"] == 3


def test_partition_commit_uses_demoted_subs_not_raw_llm_payload(monkeypatch):
    """Singleton sub demotion must survive into SPLIT_CONCEPT (not re-read from raw payload)."""
    project_id = "proj_singleton_demotion_commit"
    hub = GraphNode(
        _id="hub_thin_sub",
        node_type="CONCEPT",
        title="Clustered Hub",
        description="Hub with three neighbors.",
        project_ids=[project_id],
        metadata={"immutable": False},
    )
    db_engine.upsert_node(hub)
    for i in range(3):
        db_engine.upsert_node(
            GraphNode(
                _id=f"imm_thin_{i}",
                node_type="CONCEPT",
                title=f"Leaf {i}",
                project_ids=[project_id],
                metadata={"immutable": True},
            )
        )
        db_engine.upsert_edge(
            GraphEdge(
                _id=f"edge_thin_{i}",
                source_id=f"imm_thin_{i}",
                target_id="hub_thin_sub",
                description="linked",
                project_ids=[project_id],
            )
        )

    thin_payload = {
        "parent_title": "Clustered Hub",
        "parent_description": "Updated umbrella.",
        "sub_concepts": [
            {
                "sub_id_alias": "sub_1",
                "title": "Main Sub",
                "description": "Primary grouping.",
            },
            {
                "sub_id_alias": "sub_2",
                "title": "Thin Sub",
                "description": "Should be demoted.",
            },
        ],
        "overflow_neighbors": [],
        "rewired_edges": [
            {
                "neighbor_index": 1,
                "connect_to_sub_alias": "sub_1",
                "description": "a",
            },
            {
                "neighbor_index": 2,
                "connect_to_sub_alias": "sub_1",
                "description": "b",
            },
            {
                "neighbor_index": 3,
                "connect_to_sub_alias": "sub_2",
                "description": "singleton",
            },
        ],
    }

    def mock_chat_completion(messages, **kwargs):
        sys_content = messages[0]["content"]
        if "reorganize_discover" in sys_content or "candidates" in sys_content:
            return '{"candidates": [{"candidate_index": 1, "rationale": "Degree 3"}]}'
        if "unified partition" in sys_content.lower():
            return json.dumps(thin_payload)
        return "{}"

    from app.services.llm_gateway import llm_gateway

    monkeypatch.setattr(llm_gateway, "generate_chat_completion", mock_chat_completion)

    agent = GraphNavigator("global")
    res = agent.reorganize_overclustered_nodes(
        explored_nodes=[hub],
        project_id=project_id,
        degree_threshold=3,
        plan_only=True,
    )
    assert len(res["commands"]) == 1
    cmd = res["commands"][0]
    assert len(cmd["sub_concepts"]) == 1
    assert cmd["sub_concepts"][0]["sub_id_alias"] == "sub_1"
    demote_events = [
        e
        for e in res.get("emitted_events", [])
        if e.get("event") == "reorg_singleton_sub_demoted"
    ]
    assert len(demote_events) == 1
    assert demote_events[0]["sub_id_alias"] == "sub_2"
