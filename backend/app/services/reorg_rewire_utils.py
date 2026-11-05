"""Shared reorg rewire closure and hub neighbor discovery (scratchpad v0.2.2)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.db import db_engine
from app.models import GraphEdge
from app.services.graph_analytics import MutableTreeIndex

OVERFLOW_REWIRE_ALIASES = frozenset(
    {
        "UNCLUSTERED",
        "MISC",
        "PARENT",
        "ANCESTOR",
        "EVERYTHING",
    }
)


def is_overflow_rewire_alias(sub_alias: str) -> bool:
    """Aliases that keep neighbors on the split target (Genesis / parent), not a new wrapper."""
    return (sub_alias or "").upper() in OVERFLOW_REWIRE_ALIASES


def sub_aliases_with_assigned_neighbors(
    rewired_edges: List[Dict[str, Any]],
) -> Set[str]:
    """Sub-concept aliases that receive at least one neighbor in a rewire batch."""
    used: Set[str] = set()
    for rewired in rewired_edges:
        if not rewired.get("neighbor_id"):
            continue
        alias = (rewired.get("connect_to_sub_alias") or "").strip()
        if not alias or is_overflow_rewire_alias(alias):
            continue
        used.add(alias)
    return used


def _is_subset_edge(edge: GraphEdge) -> bool:
    desc = (edge.description or "").upper()
    return "SUBSET_OF" in desc or "SUBSET" in desc


def _skip_tree_parent_backbone(
    split_target_id: str, nb_id: str, edge: GraphEdge, project_scope: Optional[str]
) -> bool:
    """SUBSET_OF link to tree parent is structural, not a partition neighbor."""
    tree = MutableTreeIndex(project_id=project_scope)
    parent_id = tree.parent_of(split_target_id)
    if not parent_id or nb_id != parent_id:
        return False
    return _is_subset_edge(edge)


def hub_neighbor_relations(
    split_target_id: str, project_scope: Optional[str]
) -> Dict[str, str]:
    """Map neighbor_id -> relation description for non-ROOT nodes adjacent to split_target."""
    relations: Dict[str, str] = {}
    for e in db_engine.get_edges(project_scope):
        nb_id: Optional[str] = None
        if e.source_id == split_target_id:
            nb_id = e.target_id
        elif e.target_id == split_target_id:
            nb_id = e.source_id
        else:
            continue
        if not nb_id or nb_id in relations:
            continue
        if _skip_tree_parent_backbone(split_target_id, nb_id, e, project_scope):
            continue
        nb = db_engine.get_node(nb_id)
        if not nb or nb.is_root_node:
            continue
        relations[nb_id] = e.description or "RELEVANT_TO"
    return relations


def max_allowed_sub_concepts(neighbor_count: int) -> int:
    """Upper bound on sub-concepts for partition (⌊n/2⌋ compression invariant)."""
    return max(2, neighbor_count // 2)


def validate_reorg_partition(
    sub_concepts: List[Dict[str, Any]],
    overflow_neighbors: List[Dict[str, Any]],
    sub_rewired_edges: List[Dict[str, Any]],
    *,
    neighbor_count: int,
    min_sub_neighbors: int = 2,
) -> Tuple[bool, List[str]]:
    """
    Validate three-list partition output (LLM contract). Does not mutate payload.
    """
    errors: List[str] = []
    if neighbor_count < 1:
        errors.append("neighbor_count must be positive.")
        return False, errors

    expected = set(range(1, neighbor_count + 1))

    if len(sub_concepts) < 1:
        errors.append("At least one sub_concept is required.")

    max_subs = max_allowed_sub_concepts(neighbor_count)
    if len(sub_concepts) > max_subs:
        errors.append(
            f"Too many sub_concepts ({len(sub_concepts)}); maximum is {max_subs} for n={neighbor_count}."
        )

    sub_aliases = {
        (s.get("sub_id_alias") or "").strip()
        for s in sub_concepts
        if s.get("sub_id_alias")
    }

    sub_indices: Set[int] = set()
    alias_loads: Dict[str, int] = defaultdict(int)

    for edge in sub_rewired_edges:
        alias = (edge.get("connect_to_sub_alias") or "").strip()
        idx = edge.get("neighbor_index")
        if is_overflow_rewire_alias(alias):
            errors.append(
                f"rewired_edges must not use overflow alias '{alias}' "
                "(use overflow_neighbors instead)."
            )
            continue
        if idx is None:
            errors.append("rewired_edges entry missing neighbor_index.")
            continue
        if idx in sub_indices:
            errors.append(f"Duplicate neighbor_index {idx} in rewired_edges.")
        sub_indices.add(idx)
        if alias not in sub_aliases:
            errors.append(
                f"rewired_edges references unknown sub alias '{alias}' (neighbor_index={idx})."
            )
        else:
            alias_loads[alias] = alias_loads.get(alias, 0) + 1

    overflow_indices: Set[int] = set()
    for item in overflow_neighbors:
        idx = item.get("neighbor_index")
        if idx is None:
            errors.append("overflow_neighbors entry missing neighbor_index.")
            continue
        if idx in overflow_indices:
            errors.append(f"Duplicate neighbor_index {idx} in overflow_neighbors.")
        overflow_indices.add(idx)

    overlap = sub_indices & overflow_indices
    if overlap:
        errors.append(
            f"neighbor_index overlap between rewired_edges and overflow_neighbors: {sorted(overlap)}."
        )

    covered = sub_indices | overflow_indices
    missing = expected - covered
    extra = covered - expected
    if missing:
        errors.append(
            f"Missing neighbor indices (1..{neighbor_count}): {sorted(missing)}."
        )
    if extra:
        errors.append(
            f"Unknown neighbor indices outside partition batch: {sorted(extra)}."
        )

    for alias in sub_aliases:
        load = alias_loads.get(alias, 0)
        if load < min_sub_neighbors:
            errors.append(
                f"Sub '{alias}' has {load} neighbor(s) in rewired_edges; "
                f"minimum is {min_sub_neighbors} (move singletons to overflow_neighbors)."
            )

    for alias, load in alias_loads.items():
        if alias not in sub_aliases:
            errors.append(f"rewired_edges uses undeclared sub alias '{alias}'.")

    return len(errors) == 0, errors


def merge_partition_to_engine_rewires(
    sub_rewired_edges: List[Dict[str, Any]],
    overflow_neighbors: List[Dict[str, Any]],
    overflow_alias: str,
) -> List[Dict[str, Any]]:
    """Combine sub-only rewired_edges with overflow_neighbors for engine commit."""
    merged: List[Dict[str, Any]] = []
    for edge in sub_rewired_edges:
        merged.append(dict(edge))
    for item in overflow_neighbors:
        idx = item.get("neighbor_index")
        if idx is None:
            continue
        merged.append(
            {
                "neighbor_index": idx,
                "connect_to_sub_alias": overflow_alias,
                "relation_type": "RELEVANT_TO",
                "description": item.get("rationale") or "Overflow neighbor promotion.",
            }
        )
    return merged


def finalize_rewire_edges(
    split_target_id: str,
    project_scope: Optional[str],
    rewired_edges: List[Dict[str, Any]],
    *,
    is_genesis_split: bool,
    explicit_neighbor_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Ensure every hub neighbor in scope appears once in rewired_edges.
    Missing neighbors orphan to ANCESTOR (non-Genesis) or EVERYTHING (Genesis).
    """
    expected: Set[str]
    if explicit_neighbor_ids is not None:
        expected = set(explicit_neighbor_ids)
    else:
        expected = set(hub_neighbor_relations(split_target_id, project_scope).keys())

    result: List[Dict[str, Any]] = list(rewired_edges)
    covered = {r.get("neighbor_id") for r in result if r.get("neighbor_id")}

    orphan_alias = "EVERYTHING" if is_genesis_split else "ANCESTOR"
    relations = hub_neighbor_relations(split_target_id, project_scope)
    for nid in expected:
        if nid in covered:
            continue
        result.append(
            {
                "neighbor_id": nid,
                "connect_to_sub_alias": orphan_alias,
                "relation_type": relations.get(nid, "RELEVANT_TO"),
                "description": "Closure default orphan promotion.",
            }
        )
        covered.add(nid)

    return result


def resolve_rewire_relation_type(
    neighbor_id: str,
    split_target_id: str,
    current_edges: List[GraphEdge],
    llm_relation: Optional[str],
) -> str:
    """Preserve SUBSET_OF for mutable tree children when reparenting under a split."""
    nb = db_engine.get_node(neighbor_id)
    for old in current_edges:
        if old.source_id == neighbor_id and old.target_id == split_target_id:
            if _is_subset_edge(old) and nb and not nb.is_immutable:
                return "SUBSET_OF"
            return (llm_relation or old.description or "RELEVANT_TO").strip()
        if old.source_id == split_target_id and old.target_id == neighbor_id:
            if _is_subset_edge(old) and nb and not nb.is_immutable:
                return "SUBSET_OF"
            return (llm_relation or old.description or "RELEVANT_TO").strip()
    return (llm_relation or "RELEVANT_TO").strip()
