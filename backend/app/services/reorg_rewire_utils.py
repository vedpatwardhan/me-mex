"""Shared reorg rewire closure and hub neighbor discovery (scratchpad v0.2.2)."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.db import db_engine
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


def _skip_partition_neighbor(
    hub_id: str,
    nb_id: str,
    tree: MutableTreeIndex,
    nb_node: Optional[Any],
) -> bool:
    """Exclude only the split hub's recorded parent (overflow promotion target)."""
    parent_id = tree.parent_of(hub_id)
    if parent_id and nb_id == parent_id:
        return True
    return False


def hub_neighbor_ids(split_target_id: str, project_scope: Optional[str]) -> Set[str]:
    """Direct non-root graph neighbors of split_target (undifferentiated edges)."""
    tree = MutableTreeIndex(project_id=project_scope)
    neighbor_ids: Set[str] = set()
    for e in db_engine.get_edges(project_scope):
        nb_id: Optional[str] = None
        if e.source_id == split_target_id:
            nb_id = e.target_id
        elif e.target_id == split_target_id:
            nb_id = e.source_id
        else:
            continue
        if not nb_id or nb_id in neighbor_ids:
            continue
        nb = db_engine.get_node(nb_id)
        if not nb or nb.is_root_node:
            continue
        if _skip_partition_neighbor(split_target_id, nb_id, tree, nb):
            continue
        neighbor_ids.add(nb_id)
    return neighbor_ids


def partition_neighbor_count(split_target_id: str, project_scope: Optional[str]) -> int:
    """Partition batch size: direct neighbors minus tree parent (Genesis has no parent)."""
    return len(hub_neighbor_ids(split_target_id, project_scope))


def max_allowed_sub_concepts(neighbor_count: int) -> int:
    """Upper bound on sub-concepts for partition (⌊n/2⌋ compression invariant)."""
    return max(2, neighbor_count // 2)


def normalize_partition_singleton_subs(
    sub_concepts: List[Dict[str, Any]],
    overflow_neighbors: List[Dict[str, Any]],
    sub_rewired_edges: List[Dict[str, Any]],
) -> Tuple[
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
    List[Dict[str, Any]],
]:
    """
    Demote sub-concepts that only have one neighbor in rewired_edges: move that neighbor to
    overflow_neighbors and drop the sub from sub_concepts. Does not mint thin subs.

    Returns (sub_concepts, overflow_neighbors, sub_rewired_edges, demotions) where demotions
    is a list of dicts: sub_id_alias, neighbor_index, rationale (for logging/events).
    """
    subs = [dict(s) for s in sub_concepts]
    overflow = [dict(o) for o in overflow_neighbors]
    edges = [dict(e) for e in sub_rewired_edges]

    alias_loads: Dict[str, int] = defaultdict(int)
    for edge in edges:
        if edge.get("connect_to_existing_neighbor_index") is not None:
            continue
        alias = (edge.get("connect_to_sub_alias") or "").strip()
        idx = edge.get("neighbor_index")
        if is_overflow_rewire_alias(alias):
            continue
        if idx is None or not alias:
            continue
        alias_loads[alias] = alias_loads.get(alias, 0) + 1

    sub_aliases = {
        (s.get("sub_id_alias") or "").strip() for s in subs if s.get("sub_id_alias")
    }

    demotions: List[Dict[str, Any]] = []
    singleton_aliases = {
        a
        for a in sub_aliases
        if alias_loads.get(a, 0) == 1 and not is_overflow_rewire_alias(a)
    }

    overflow_indices = {
        o.get("neighbor_index") for o in overflow if o.get("neighbor_index") is not None
    }

    for alias in sorted(singleton_aliases):
        # Find the single rewired_edges row for this alias
        row_idx = None
        nidx = None
        for i, edge in enumerate(edges):
            a = (edge.get("connect_to_sub_alias") or "").strip()
            if a != alias or is_overflow_rewire_alias(a):
                continue
            row_idx = i
            nidx = edge.get("neighbor_index")
            break
        if row_idx is None or nidx is None:
            continue

        rationale = (
            "Server-side demotion: sub-concept had only one neighbor in rewired_edges; "
            "skipping mint and treating as overflow (orphan to ancestor/Everything at commit)."
        )

        del edges[row_idx]
        subs = [s for s in subs if (s.get("sub_id_alias") or "").strip() != alias]

        if nidx in overflow_indices:
            demotions.append(
                {
                    "sub_id_alias": alias,
                    "neighbor_index": nidx,
                    "rationale": rationale
                    + " (neighbor_index already in overflow; edge removed only.)",
                }
            )
            continue

        overflow.append({"neighbor_index": nidx, "rationale": rationale})
        overflow_indices.add(nidx)
        demotions.append(
            {
                "sub_id_alias": alias,
                "neighbor_index": nidx,
                "rationale": rationale,
            }
        )

    return subs, overflow, edges, demotions


def repair_partition_self_loop_rewires(
    payload: Dict[str, Any],
    *,
    is_replacement_split: bool,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Fix LLM confusion on replacement split: neighbor_index == connect_to_existing_neighbor_index
    when the model meant to assign the sub_1 cluster (parent id reuse), not self-attach.
    """
    data = json.loads(json.dumps(payload))
    repairs: List[str] = []
    edges = list(data.get("rewired_edges") or [])
    sub_aliases = {
        (s.get("sub_id_alias") or "").strip()
        for s in (data.get("sub_concepts") or [])
        if s.get("sub_id_alias")
    }
    for i, edge in enumerate(edges):
        idx = edge.get("neighbor_index")
        existing = edge.get("connect_to_existing_neighbor_index")
        if existing is None or idx != existing:
            continue
        if is_replacement_split:
            fixed = dict(edge)
            fixed.pop("connect_to_existing_neighbor_index", None)
            fixed["connect_to_sub_alias"] = "sub_1"
            edges[i] = fixed
            repairs.append(
                f"neighbor_index {idx}: self connect_to_existing_neighbor_index "
                "rewritten to connect_to_sub_alias sub_1 (replacement split)."
            )
        elif "sub_1" in sub_aliases:
            fixed = dict(edge)
            fixed.pop("connect_to_existing_neighbor_index", None)
            fixed["connect_to_sub_alias"] = "sub_1"
            edges[i] = fixed
            repairs.append(
                f"neighbor_index {idx}: self-loop rewritten to connect_to_sub_alias sub_1."
            )
    data["rewired_edges"] = edges
    return data, repairs


def validate_reorg_partition(
    sub_concepts: List[Dict[str, Any]],
    overflow_neighbors: List[Dict[str, Any]],
    sub_rewired_edges: List[Dict[str, Any]],
    *,
    neighbor_count: int,
    min_sub_neighbors: int = 2,
    mutable_neighbor_indices: Optional[Set[int]] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate three-list partition output (LLM contract). Does not mutate payload.
    """
    errors: List[str] = []
    if neighbor_count < 1:
        errors.append("neighbor_count must be positive.")
        return False, errors

    expected = set(range(1, neighbor_count + 1))

    uses_new_sub = any(
        (e.get("connect_to_sub_alias") or "").strip() for e in sub_rewired_edges
    )
    uses_existing = any(
        e.get("connect_to_existing_neighbor_index") is not None
        for e in sub_rewired_edges
    )
    if uses_new_sub and len(sub_concepts) < 1:
        errors.append(
            "At least one sub_concept is required when using connect_to_sub_alias."
        )
    if not uses_new_sub and not uses_existing and not overflow_neighbors:
        errors.append(
            "rewired_edges must assign neighbors via connect_to_sub_alias "
            "or connect_to_existing_neighbor_index."
        )

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
    existing_target_indices: Set[int] = set()
    mutable_allow = (
        mutable_neighbor_indices if mutable_neighbor_indices is not None else set()
    )

    for edge in sub_rewired_edges:
        idx = edge.get("neighbor_index")
        alias = (edge.get("connect_to_sub_alias") or "").strip()
        existing_idx = edge.get("connect_to_existing_neighbor_index")

        if idx is None:
            errors.append("rewired_edges entry missing neighbor_index.")
            continue
        if idx in sub_indices:
            errors.append(f"Duplicate neighbor_index {idx} in rewired_edges.")
        sub_indices.add(idx)

        has_sub = bool(alias)
        has_existing = existing_idx is not None
        if has_sub == has_existing:
            errors.append(
                f"neighbor_index {idx}: set exactly one of connect_to_sub_alias "
                "or connect_to_existing_neighbor_index."
            )
            continue

        if has_existing:
            if existing_idx == idx:
                errors.append(
                    f"neighbor_index {idx} cannot target itself via "
                    "connect_to_existing_neighbor_index."
                )
            elif existing_idx not in expected:
                errors.append(
                    f"connect_to_existing_neighbor_index {existing_idx} outside "
                    f"partition batch (1..{neighbor_count})."
                )
            elif (
                mutable_neighbor_indices is not None
                and existing_idx not in mutable_allow
            ):
                errors.append(
                    f"connect_to_existing_neighbor_index {existing_idx} must "
                    "reference a mutable neighbor in the batch."
                )
            else:
                existing_target_indices.add(existing_idx)
            continue

        if is_overflow_rewire_alias(alias):
            errors.append(
                f"rewired_edges must not use overflow alias '{alias}' "
                "(use overflow_neighbors instead)."
            )
            continue
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

    anchor_only = existing_target_indices - sub_indices - overflow_indices
    covered = sub_indices | overflow_indices
    missing = expected - covered - anchor_only
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


CLOSURE_ORPHAN_DESCRIPTION = "Closure default orphan promotion."


def partition_rewire_assignment_kind(
    edge: Dict[str, Any], *, overflow_alias: str
) -> str:
    """Classify a resolved partition rewire row for telemetry."""
    if edge.get("connect_to_target_id"):
        return "reuse_existing"
    alias = (edge.get("connect_to_sub_alias") or "").strip()
    if edge.get("description") == CLOSURE_ORPHAN_DESCRIPTION:
        return "overflow_closure"
    if alias and is_overflow_rewire_alias(alias):
        return "overflow"
    if alias.upper() == (overflow_alias or "").strip().upper() and alias:
        return "overflow"
    if alias:
        return "mint"
    return "unknown"


def summarize_partition_rewire_plan(
    rewired_edges: List[Dict[str, Any]],
    *,
    overflow_alias: str,
    new_sub_concepts: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate mint vs reuse vs overflow counts for partition_completed events."""
    mint_sub_aliases: Set[str] = set()
    for edge in rewired_edges:
        kind = edge.get("assignment_kind") or partition_rewire_assignment_kind(
            edge, overflow_alias=overflow_alias
        )
        edge["assignment_kind"] = kind
        if kind == "mint":
            alias = (edge.get("connect_to_sub_alias") or "").strip()
            if alias:
                mint_sub_aliases.add(alias)
    kinds = [e.get("assignment_kind", "unknown") for e in rewired_edges]
    return {
        "new_sub_concepts_planned": len(new_sub_concepts),
        "mint_sub_aliases": sorted(mint_sub_aliases),
        "mint_assignment_count": kinds.count("mint"),
        "reuse_existing_assignment_count": kinds.count("reuse_existing"),
        "overflow_assignment_count": kinds.count("overflow"),
        "overflow_closure_assignment_count": kinds.count("overflow_closure"),
    }


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
        expected = hub_neighbor_ids(split_target_id, project_scope)

    result: List[Dict[str, Any]] = list(rewired_edges)
    covered = {r.get("neighbor_id") for r in result if r.get("neighbor_id")}

    orphan_alias = "EVERYTHING" if is_genesis_split else "ANCESTOR"
    for nid in expected:
        if nid in covered:
            continue
        result.append(
            {
                "neighbor_id": nid,
                "connect_to_sub_alias": orphan_alias,
                "description": CLOSURE_ORPHAN_DESCRIPTION,
                "assignment_kind": "overflow_closure",
            }
        )
        covered.add(nid)

    return result
