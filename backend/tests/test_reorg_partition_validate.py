"""Validator and merge for three-list reorg partition (v0.2.5)."""

import pytest

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
