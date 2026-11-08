"""
Graph Navigator: Me-Mex v0.2

Genesis-rooted mutable tree traversal, intra-document linking, and selective reorganization.
"""

import json
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional, Set
from app.db import db_engine
from app.config import settings
from app.models import (
    GraphNode,
    GraphEdge,
    ReorgDiscoveryPayload,
    ReorgPartitionPayload,
    PersonaIngestionCommandsPayload,
    PersonaExplorationPayload,
)
from app.services.graph_analytics import MutableTreeIndex, graph_analytics
from app.services.graph_ingestion_engine import (
    GraphIngestionEngine,
    _is_genesis,
    graph_ingestion_engine,
)
from app.services.reorg_queue import ReorgQueue, ReorgWorkItem
from app.services.logger import logger
from app.services.ingest_payload import json_dumps_ingest
from app.services.reorg_rewire_utils import (
    finalize_rewire_edges,
    max_allowed_sub_concepts,
    merge_partition_to_engine_rewires,
    normalize_partition_singleton_subs,
    validate_reorg_partition,
)
from app.services.llm_gateway import llm_gateway
from app.services.prompt_mapper import PromptIdMapper
from app.prompts import load_prompt


def _append_reorg_event(
    emitted_events: List[Dict[str, Any]],
    project_id: str,
    payload: Dict[str, Any],
) -> None:
    """Append telemetry and mirror to Rich console in execution order."""
    emitted_events.append(payload)
    event_type = payload.get("event") or "reorg"
    logger.log_event(project_id, event_type, payload)


def _genesis_cascade_allowed(
    tree: MutableTreeIndex,
    *,
    hub_id: str,
    genesis_id: str,
    link_affected_ids: Set[str],
) -> bool:
    if genesis_id in link_affected_ids:
        return True
    return tree.parent_of(hub_id) == genesis_id


def _reorg_split_strategy_block(is_genesis: bool) -> tuple[str, str]:
    """Genesis wrapper vs replacement split instructions and overflow alias for prompts."""
    if is_genesis:
        block = (
            "GENESIS (Everything) — WRAPPER SPLIT:\n"
            "- Mint sub-hubs that live **under** Everything (Genesis is preserved; title stays 'Everything').\n"
            "- Maximize assignment of neighbors to new sub-hubs beneath Genesis."
        )
        return block, "EVERYTHING"
    block = (
        "REPLACEMENT SPLIT:\n"
        "- **`sub_1` reuses the split target node id** as the replacement hub — assign the "
        "largest coherent neighbor cluster to `sub_1` when possible.\n"
        "- Additional sub-concepts (`sub_2`, …) are new siblings under the tree parent "
        "(same depth; no new wrapper layer under the old hub)."
    )
    return block, "ANCESTOR"


from app.tools.search_tools import search_tools


class GraphNavigator:
    """Single navigator for Genesis-rooted tree traversal and graph maintenance."""

    def __init__(self, project_id: str = "global"):
        self.project_id = project_id
        self.genesis_node = db_engine.get_genesis_node(project_id)
        if not self.genesis_node:
            raise ValueError(f"Genesis node missing for project '{project_id}'")
        self.scope_node = self.genesis_node
        self.navigator_id = f"nav_{self.genesis_node.id}"
        self.navigator_name = "Graph Navigator"
        self.last_explored_nodes: List[GraphNode] = [self.genesis_node]

    @property
    def department_id(self) -> str:
        return self.navigator_id

    @property
    def department_name(self) -> str:
        return self.navigator_name

    @staticmethod
    def _get_adjacency_map(project_id: str) -> Dict[str, List[GraphEdge]]:
        """Constructs an undirected adjacency map of edges for the given project."""
        all_edges = db_engine.get_edges(project_id)
        adj_map: Dict[str, List[GraphEdge]] = defaultdict(list)
        for e in all_edges:
            adj_map[e.source_id].append(e)
            adj_map[e.target_id].append(e)
        return adj_map

    @classmethod
    def get_candidate_neighbors(
        cls,
        frontier_ids: List[str],
        adj_map: Dict[str, List[GraphEdge]],
        visited_ids: set,
        partition_node_ids: Optional[set] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Discovers unvisited valid non-root neighbors connected to current frontier nodes."""
        candidate_neighbors: Dict[str, Dict[str, Any]] = {}
        for f_id in frontier_ids:
            f_node = db_engine.get_node(f_id)
            if f_node and f_node.is_root_node:
                continue

            for e in adj_map.get(f_id, []):
                neighbor_id = e.target_id if e.source_id == f_id else e.source_id
                if partition_node_ids and neighbor_id not in partition_node_ids:
                    continue

                if (
                    neighbor_id not in visited_ids
                    and neighbor_id not in candidate_neighbors
                ):
                    neighbor_node = db_engine.get_node(neighbor_id)
                    if neighbor_node and not neighbor_node.is_root_node:
                        candidate_neighbors[neighbor_id] = {
                            "id": neighbor_node.id,
                            "title": neighbor_node.title,
                            "body": neighbor_node.description,
                            "node_type": neighbor_node.node_type,
                            "immutable": neighbor_node.is_immutable,
                        }
        return candidate_neighbors

    @classmethod
    def get_tree_mutable_candidates(
        cls,
        frontier_ids: List[str],
        tree: MutableTreeIndex,
        visited_ids: set,
    ) -> Dict[str, Dict[str, Any]]:
        """Mutable tree children plus direct immutable context (immutable not expandable)."""
        candidate_neighbors: Dict[str, Dict[str, Any]] = {}
        for f_id in frontier_ids:
            for child in tree.mutable_children(f_id):
                if child.id in visited_ids or child.id in candidate_neighbors:
                    continue
                candidate_neighbors[child.id] = {
                    "id": child.id,
                    "title": child.title,
                    "body": child.description,
                    "description": child.description,
                    "node_type": child.node_type,
                    "immutable": False,
                }
            for imm in tree.direct_immutable_neighbors(f_id):
                if imm.id in visited_ids or imm.id in candidate_neighbors:
                    continue
                candidate_neighbors[imm.id] = {
                    "id": imm.id,
                    "title": imm.title,
                    "body": imm.description,
                    "description": imm.description,
                    "node_type": imm.node_type,
                    "immutable": True,
                }
        return candidate_neighbors

    def explore_for_retrieval(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.traverse_mutable_tree_from_genesis(
            query=query,
            chat_history=chat_history,
            project_id=project_id,
            traversal_top_k=settings.RETRIEVAL_TRAVERSAL_TOP_K,
        )

    def traverse_mutable_tree_from_genesis(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: Optional[str] = None,
        max_depth: Optional[int] = None,
        allow_web_search: bool = False,
        traversal_top_k: Optional[int] = None,
        ingest_context_messages: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Top-down traversal from Genesis over the mutable tree backbone."""
        pid = project_id or self.project_id
        max_traversal_depth = (
            max_depth if max_depth is not None else settings.MAX_TRAVERSAL_DEPTH
        )
        hop_top_k = traversal_top_k
        if hop_top_k is None:
            hop_top_k = settings.INGEST_TRAVERSAL_TOP_K
        tree = MutableTreeIndex(project_id=pid)

        visited_node_ids = set([self.genesis_node.id])
        current_frontier = [self.genesis_node.id]
        explored_nodes_map: Dict[str, GraphNode] = {
            self.genesis_node.id: self.genesis_node
        }
        emitted_events: List[Dict[str, Any]] = []

        # Emit node_touched event for Hop 0 Genesis anchor
        genesis_touch_evt = {
            "event": "node_touched",
            "persona_id": self.department_id,
            "persona_name": self.department_name,
            "node_id": self.genesis_node.id,
            "node_title": self.genesis_node.title,
            "message": f"Concept '{self.genesis_node.title}' touched by {self.department_name}.",
            "timestamp": time.time(),
        }
        emitted_events.append(genesis_touch_evt)

        for hop in range(1, max_traversal_depth + 1):
            if not current_frontier:
                break

            candidate_neighbors = self.get_tree_mutable_candidates(
                frontier_ids=current_frontier,
                tree=tree,
                visited_ids=visited_node_ids,
            )

            if not candidate_neighbors:
                break

            # Evaluate candidate neighbors with persona LLM
            # Concept Cache Map for Candidate Neighbors in subgraph expansion
            expansion_mapper = PromptIdMapper(prefix="concept")
            indexed_candidate_neighbors = []
            for n_id, n_data in candidate_neighbors.items():
                n_idx = expansion_mapper.register(n_id)
                indexed_candidate_neighbors.append(
                    {
                        "neighbor_index": n_idx,
                        "title": n_data.get("title", ""),
                        "description": n_data.get("description", ""),
                        "node_type": n_data.get("node_type", "concept"),
                        "immutable": n_data.get("immutable", False),
                    }
                )

            prompt_payload = f"""Genesis / Project Scope (Everything):
{self.genesis_node.description}

Current traversal frontier node: '{current_frontier[0] if current_frontier else self.genesis_node.title}'
User Query / Context: "{query}"
Current Hop Level: {hop} / {max_traversal_depth}

Candidate Unvisited Neighbor Concepts ({len(indexed_candidate_neighbors)} items):
{json_dumps_ingest(indexed_candidate_neighbors)}"""
            messages = [
                {
                    "role": "system",
                    "content": load_prompt(
                        "graph_tree_traversal",
                        genesis_title=self.genesis_node.title,
                        max_depth=max_traversal_depth,
                        traversal_top_k=hop_top_k,
                    ),
                }
            ]
            if ingest_context_messages:
                messages.extend(ingest_context_messages)
            elif chat_history:
                messages.extend(chat_history[-4:])
            messages.append({"role": "user", "content": prompt_payload})

            try:
                payload = llm_gateway.generate_structured_completion(
                    messages,
                    response_model=PersonaExplorationPayload,
                    temperature=0.2,
                    max_tokens=1024,
                    max_retries=2,
                    enable_reasoning=False,
                    caller=f"GraphNavigator[{self.department_name}].subgraph_expansion",
                )
                # Decode integer neighbor_index back to real string node_id
                neighbor_rationales: Dict[str, str] = {}
                for item in payload.selected_neighbors:
                    real_node_id = expansion_mapper.to_id(item.neighbor_index)
                    if real_node_id and real_node_id in candidate_neighbors:
                        # Defensive guard: exploration is only permitted on mutable nodes
                        if candidate_neighbors[real_node_id]["immutable"]:
                            continue
                        neighbor_rationales[real_node_id] = item.rationale
                next_frontier = list(neighbor_rationales.keys())
                if hop_top_k is not None and hop_top_k > 0:
                    truncated = len(next_frontier) > hop_top_k
                    next_frontier = next_frontier[:hop_top_k]
                    if truncated:
                        emitted_events.append(
                            {
                                "event": "traversal_neighbors_truncated",
                                "hop": hop,
                                "top_k": hop_top_k,
                                "timestamp": time.time(),
                            }
                        )
            except Exception as e:
                print(f"[{self.department_name}] Subgraph expansion error: {e}")
                raise RuntimeError(
                    f"[{self.department_name}] Subgraph expansion failed: {e}"
                ) from e

            for nid in next_frontier:
                visited_node_ids.add(nid)
                n_node = db_engine.get_node(nid)
                if n_node:
                    explored_nodes_map[nid] = n_node
                    rationale = neighbor_rationales.get(nid, "")
                    # Emit real-time telemetry event
                    evt = {
                        "event": "node_touched",
                        "persona_id": self.department_id,
                        "persona_name": self.department_name,
                        "node_id": n_node.id,
                        "node_title": n_node.title,
                        "rationale": rationale,
                        "message": (
                            f"Concept '{n_node.title}' explored at hop {hop}: {rationale}"
                            if rationale
                            else f"Concept '{n_node.title}' explored at hop {hop} by {self.department_name}."
                        ),
                        "timestamp": time.time(),
                    }
                    emitted_events.append(evt)

            current_frontier = next_frontier

        self.last_explored_nodes = list(explored_nodes_map.values())
        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "genesis_node_id": self.genesis_node.id,
            "explored_nodes": self.last_explored_nodes,
            "traversed_node_ids": list(visited_node_ids),
            "emitted_events": emitted_events,
        }

    def _execute_split_and_rewire(
        self,
        target_node: GraphNode,
        mode: str,
        target_neighbors_to_rewire: List[Dict[str, Any]],
        project_id: str,
        emitted_events: List[Dict[str, Any]],
        degree_threshold: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Unified partition: sub-concepts + overflow_neighbors + sub-only rewired_edges."""
        n_neighbors = len(target_neighbors_to_rewire)
        if not n_neighbors:
            return None

        tau = (
            degree_threshold
            if degree_threshold is not None
            else settings.DEGREE_THRESHOLD
        )
        tree = MutableTreeIndex(project_id=project_id)
        current_degree = tree.effective_degree(target_node.id)

        max_allowed_subs = max_allowed_sub_concepts(n_neighbors)
        is_genesis_hub = bool(
            target_node.metadata.get("is_genesis")
            or target_node.title.strip().lower() == "everything"
        )
        split_strategy_block, overflow_alias = _reorg_split_strategy_block(
            is_genesis_hub
        )
        overflow_target_label = (
            "Everything (Genesis)" if is_genesis_hub else "the tree ancestor"
        )
        system_partition = load_prompt(
            "graph_reorg_partition",
            department_name=self.department_name,
            node_id=target_node.id,
            mode=mode,
            split_strategy_block=split_strategy_block,
            overflow_target_label=overflow_target_label,
            min_sub_concepts=1,
            min_sub_neighbors=2,
            max_allowed_sub_concepts=max_allowed_subs,
            neighbor_count=n_neighbors,
        )

        rewire_concept_mapper = PromptIdMapper(prefix="concept")
        indexed_neighbors_to_rewire = []
        for nb in target_neighbors_to_rewire:
            nb_idx = rewire_concept_mapper.register(nb["id"])
            entry = dict(nb)
            entry["neighbor_index"] = nb_idx
            entry.pop("id", None)
            indexed_neighbors_to_rewire.append(entry)

        user_partition = "\n\n".join(
            [
                f"Target over-clustered mutable concept: '{target_node.title}' (ID: {target_node.id})",
                f"Current Description: {target_node.description}",
                f"Reorganization Mode: {mode}",
                f"Current effective_degree: {current_degree} (threshold τ = {tau})",
                "Target: after split, parent/orphan load should trend toward < τ where possible.",
                f"Neighbors to assign: n = {n_neighbors} (max subs ≤ {max_allowed_subs})",
                f"Target Neighbors to Partition ({len(indexed_neighbors_to_rewire)} items):",
                json_dumps_ingest(indexed_neighbors_to_rewire),
            ]
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_partition},
            {"role": "user", "content": user_partition},
        ]
        partition_attempts = 3
        payload: Optional[ReorgPartitionPayload] = None
        validation_errors: List[str] = []

        for attempt in range(1, partition_attempts + 1):
            try:
                payload = llm_gateway.generate_structured_completion(
                    messages,
                    response_model=ReorgPartitionPayload,
                    temperature=0.2,
                    max_tokens=settings.REORG_PARTITION_MAX_TOKENS,
                    max_retries=2,
                    enable_reasoning=settings.REORG_PARTITION_ENABLE_REASONING,
                    caller=f"GraphNavigator[{self.department_name}].reorg_partition_{mode}",
                )
            except Exception as e:
                if attempt >= partition_attempts:
                    raise RuntimeError(
                        f"[{self.department_name}] Unified partition failed for "
                        f"{target_node.id} (mode={mode}): {e}"
                    ) from e
                continue

            formulated_subs = [s.model_dump() for s in payload.sub_concepts]
            overflow_raw = [o.model_dump() for o in payload.overflow_neighbors]
            sub_rewired_raw = [r.model_dump() for r in payload.rewired_edges]

            (
                formulated_subs,
                overflow_raw,
                sub_rewired_raw,
                singleton_demotions,
            ) = normalize_partition_singleton_subs(
                formulated_subs,
                overflow_raw,
                sub_rewired_raw,
            )
            for dem in singleton_demotions:
                nb_id = rewire_concept_mapper.to_id(dem.get("neighbor_index"))
                msg = (
                    f"[{self.department_name}] Singleton sub-concept demotion "
                    f"(hub '{target_node.title}' / {target_node.id}): "
                    f"alias={dem.get('sub_id_alias')} neighbor_index={dem.get('neighbor_index')} "
                    f"neighbor_id={nb_id} — skipping thin sub, neighbor promoted via overflow."
                )
                _append_reorg_event(
                    emitted_events,
                    project_id,
                    {
                        "event": "reorg_singleton_sub_demoted",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "node_id": target_node.id,
                        "node_title": target_node.title,
                        "sub_id_alias": dem.get("sub_id_alias"),
                        "neighbor_index": dem.get("neighbor_index"),
                        "neighbor_id": nb_id,
                        "rationale": dem.get("rationale"),
                        "message": msg,
                        "timestamp": time.time(),
                    },
                )

            ok, validation_errors = validate_reorg_partition(
                formulated_subs,
                overflow_raw,
                sub_rewired_raw,
                neighbor_count=n_neighbors,
            )
            if ok:
                break
            retry_msg = (
                f"[{self.department_name}] Partition validation failed for "
                f"'{target_node.title}' (attempt {attempt}/{partition_attempts}): "
                f"{'; '.join(validation_errors)}"
            )
            _append_reorg_event(
                emitted_events,
                project_id,
                {
                    "event": "reorg_partition_validation_retry",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "node_id": target_node.id,
                    "node_title": target_node.title,
                    "attempt": attempt,
                    "partition_attempts": partition_attempts,
                    "validation_errors": validation_errors,
                    "message": retry_msg,
                    "timestamp": time.time(),
                },
            )
            if attempt >= partition_attempts:
                _append_reorg_event(
                    emitted_events,
                    project_id,
                    {
                        "event": "reorg_partition_failed",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "node_id": target_node.id,
                        "node_title": target_node.title,
                        "validation_errors": validation_errors,
                        "message": (
                            f"[{self.department_name}] Partition validation failed for "
                            f"'{target_node.title}' after {partition_attempts} attempt(s)."
                        ),
                        "timestamp": time.time(),
                    },
                )
                return None
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your partition JSON failed validation. Fix and return a complete response.\n"
                        "Errors:\n- " + "\n- ".join(validation_errors)
                    ),
                }
            )

        if payload is None:
            return None

        formulated_subs = [s.model_dump() for s in payload.sub_concepts]
        overflow_raw = [o.model_dump() for o in payload.overflow_neighbors]
        sub_rewired_raw = [r.model_dump() for r in payload.rewired_edges]
        merged_raw = merge_partition_to_engine_rewires(
            sub_rewired_raw, overflow_raw, overflow_alias
        )

        rewired = []
        overflow_neighbor_ids: List[str] = []
        for r in merged_raw:
            real_nb_id = rewire_concept_mapper.to_id(r.get("neighbor_index"))
            if not real_nb_id:
                continue
            if (r.get("connect_to_sub_alias") or "").upper() == overflow_alias:
                overflow_neighbor_ids.append(real_nb_id)
            rewired.append(
                {
                    "neighbor_id": real_nb_id,
                    "connect_to_sub_alias": r.get("connect_to_sub_alias"),
                    "description": r.get("description", ""),
                }
            )

        partition_ids = [nb["id"] for nb in target_neighbors_to_rewire if nb.get("id")]
        rewired = finalize_rewire_edges(
            target_node.id,
            project_id,
            rewired,
            is_genesis_split=is_genesis_hub,
            explicit_neighbor_ids=partition_ids,
        )

        partition_event = {
            "event": "reorg_partition_completed",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "node_id": target_node.id,
            "node_title": target_node.title,
            "reorg_mode": mode,
            "validation_passed": True,
            "sub_concepts_count": len(formulated_subs),
            "sub_concepts": formulated_subs,
            "overflow_neighbors_count": len(overflow_raw),
            "overflow_neighbor_ids": overflow_neighbor_ids,
            "rewired_edges_count": len(rewired),
            "rewired_edges": rewired,
            "message": (
                f"[{self.department_name}] Partition ({mode}) completed for '{target_node.title}': "
                f"{len(formulated_subs)} sub-concept(s), {len(overflow_raw)} overflow neighbor(s), "
                f"{len(rewired)} total re-wire(s)."
            ),
            "timestamp": time.time(),
        }
        emitted_events.append(partition_event)

        return {
            "parent_title": payload.parent_title,
            "parent_description": payload.parent_description,
            "sub_concepts": formulated_subs,
            "rewired_edges": rewired,
            "overflow_neighbor_ids": overflow_neighbor_ids,
        }

    @staticmethod
    def _neighbor_entries_for_hub(
        hub_id: str, project_id: str, tree: MutableTreeIndex
    ) -> List[Dict[str, Any]]:
        """Direct neighbors eligible for partition (excludes mutable tree backbone)."""
        from app.services.reorg_rewire_utils import hub_neighbor_ids

        allowed = hub_neighbor_ids(hub_id, project_id)
        entries: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for e in db_engine.get_edges(project_id):
            nb_id = None
            direction = "incoming"
            if e.source_id == hub_id:
                nb_id = e.target_id
                direction = "outgoing"
            elif e.target_id == hub_id:
                nb_id = e.source_id
                direction = "incoming"
            else:
                continue
            if not nb_id or nb_id in seen or nb_id not in allowed:
                continue
            seen.add(nb_id)
            nb_node = db_engine.get_node(nb_id)
            if not nb_node or nb_node.is_root_node:
                continue
            entries.append(
                {
                    "id": nb_node.id,
                    "title": nb_node.title,
                    "description": nb_node.description,
                    "is_immutable": nb_node.is_immutable,
                    "node_type": nb_node.node_type,
                    "direction": direction,
                    "subtree_mut_height": tree.subtree_mut_height.get(nb_id, 0),
                }
            )
        return entries

    def build_split_command_for_hub(
        self,
        hub_id: str,
        project_id: str = "global",
        emitted_events: Optional[List[Dict[str, Any]]] = None,
        degree_threshold: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Partition + rewire for one hub (cascade path; no LLM discover)."""
        events = emitted_events if emitted_events is not None else []
        target_node = db_engine.get_node(hub_id)
        if not target_node or target_node.is_immutable:
            return None
        tree = MutableTreeIndex(project_id=project_id)
        neighbors = self._neighbor_entries_for_hub(hub_id, project_id, tree)
        if not neighbors:
            return None
        tau = (
            degree_threshold
            if degree_threshold is not None
            else settings.DEGREE_THRESHOLD
        )
        if (
            _is_genesis(target_node)
            and len(neighbors) < settings.REORG_SKIP_GENESIS_PARTITION_MIN_NEIGHBORS
        ):
            _append_reorg_event(
                events,
                project_id,
                {
                    "event": "reorg_candidate_skipped",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "concept_id": hub_id,
                    "node_title": target_node.title,
                    "reason": "genesis_insufficient_neighbors",
                    "message": (
                        f"[{self.department_name}] Skipped Genesis partition: "
                        f"{len(neighbors)} neighbors < "
                        f"{settings.REORG_SKIP_GENESIS_PARTITION_MIN_NEIGHBORS}."
                    ),
                    "timestamp": time.time(),
                },
            )
            return None
        res = self._execute_split_and_rewire(
            target_node=target_node,
            mode="max_coverage",
            target_neighbors_to_rewire=neighbors,
            project_id=project_id,
            degree_threshold=tau,
            emitted_events=events,
        )
        if not res:
            return None
        return {
            "action": "SPLIT_CONCEPT",
            "concept_id": target_node.id,
            "parent_title": res["parent_title"],
            "parent_description": res["parent_description"],
            "sub_concepts": res["sub_concepts"],
            "rewired_edges": res["rewired_edges"],
            "partition_neighbor_ids": [nb["id"] for nb in neighbors],
            "overflow_neighbor_ids": res.get("overflow_neighbor_ids", []),
        }

    def _process_reorg_queue(
        self,
        queue: ReorgQueue,
        *,
        project_id: str,
        degree_threshold: int,
        doc_title: str,
        proj_list: List[str],
        ingestion_engine: Optional[GraphIngestionEngine],
        emitted_events: List[Dict[str, Any]],
        plan_only: bool,
        node_map: Dict[str, GraphNode],
        link_affected_ids: Optional[Set[str]] = None,
    ) -> tuple[int, List[Dict[str, Any]]]:
        """
        Single Phase 4 loop: pop hub → build_split_command_for_hub → execute or collect.
        Cascade parents enqueue as hub IDs only (same pipeline at pop).
        """
        splits_executed = 0
        cascade_enqueues = 0
        collected_commands: List[Dict[str, Any]] = []
        projects = proj_list or [project_id]
        engine = ingestion_engine or graph_ingestion_engine
        split_hubs_this_pass: Set[str] = set()
        link_affected = link_affected_ids or set()

        while queue:
            item = queue.pop_front()
            if not item:
                break

            cmd = self.build_split_command_for_hub(
                item.hub_id,
                project_id=project_id,
                emitted_events=emitted_events,
                degree_threshold=degree_threshold,
            )
            if not cmd:
                target_node = node_map.get(item.hub_id) or db_engine.get_node(
                    item.hub_id
                )
                title = target_node.title if target_node else item.hub_id
                _append_reorg_event(
                    emitted_events,
                    project_id,
                    {
                        "event": "reorg_candidate_skipped",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "concept_id": item.hub_id,
                        "node_title": title,
                        "reason": "Partition returned no sub-concepts",
                        "message": (
                            f"[{self.department_name}] Skipped hub '{title}': "
                            "partition produced no split."
                        ),
                        "timestamp": time.time(),
                    },
                )
                continue

            if plan_only:
                collected_commands.append(cmd)
                continue

            cmd["navigator_id"] = self.navigator_id
            cmd["navigator_name"] = self.navigator_name
            evt = engine.execute_single_command(cmd, doc_title, projects)
            if evt:
                rewire_detail = evt.pop("rewire_events", None) or []
                for detail in rewire_detail:
                    detail.setdefault("persona_id", self.department_id)
                    detail.setdefault("department_name", self.department_name)
                    emitted_events.append(detail)
                evt["persona_id"] = self.department_id
                evt["department_name"] = self.department_name
                emitted_events.append(evt)
            splits_executed += 1
            split_hubs_this_pass.add(item.hub_id)
            graph_analytics.refresh_tree_metadata(project_id)

            hub_id = item.hub_id
            hub_node = db_engine.get_node(hub_id)
            if hub_node and _is_genesis(hub_node):
                continue

            tree = MutableTreeIndex(project_id=project_id)
            ancestor_id = tree.parent_of(hub_id)
            if not ancestor_id:
                continue
            if ancestor_id in split_hubs_this_pass:
                continue
            if queue.should_defer_parent_cascade(ancestor_id):
                continue
            if tree.effective_degree(ancestor_id) < degree_threshold:
                continue

            ancestor_node = db_engine.get_node(ancestor_id)
            if ancestor_node and _is_genesis(ancestor_node):
                if not _genesis_cascade_allowed(
                    tree,
                    hub_id=hub_id,
                    genesis_id=ancestor_id,
                    link_affected_ids=link_affected,
                ):
                    continue

            if cascade_enqueues >= settings.MAX_UPWARD_REORG_ITERATIONS:
                continue

            cascade_enqueues += 1
            _append_reorg_event(
                emitted_events,
                project_id,
                {
                    "event": "reorg_cascade_iteration",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "ancestor_id": ancestor_id,
                    "trigger_child_id": hub_id,
                    "queued_front": True,
                    "cascade_index": cascade_enqueues,
                    "message": (
                        f"[{self.department_name}] Cascade enqueue: parent "
                        f"'{ancestor_node.title if ancestor_node else ancestor_id}' "
                        f"after split of '{hub_node.title if hub_node else hub_id}'."
                    ),
                    "timestamp": time.time(),
                },
            )
            tree = MutableTreeIndex(project_id=project_id)
            queue.prepend_cascade_filo(
                ReorgWorkItem(
                    hub_id=ancestor_id,
                    kind="cascade",
                    tree_parent_id=tree.parent_of(ancestor_id),
                )
            )

        return splits_executed, collected_commands

    def reorganize_overclustered_nodes(
        self,
        seed_nodes: list[GraphNode] | None = None,
        *,
        project_id: str = "global",
        degree_threshold: Optional[int] = None,
        doc_title: str = "",
        proj_list: Optional[List[str]] = None,
        ingestion_engine: Optional[GraphIngestionEngine] = None,
        plan_only: bool = True,
        explored_nodes: list[GraphNode] | None = None,
        link_affected_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        Phase 4 reorganization: LLM discover once, then one queue (hub IDs only).
        Each dequeue runs build_split_command_for_hub → commit → optional parent enqueue.

        plan_only=True: run queue without execute (no cascade enqueue); returns commands.
        """
        seeds = seed_nodes if seed_nodes is not None else explored_nodes
        emitted_events: List[Dict[str, Any]] = []
        if not seeds:
            return {"commands": [], "emitted_events": []}

        if degree_threshold is None:
            degree_threshold = settings.DEGREE_THRESHOLD

        tree = MutableTreeIndex(project_id=project_id)
        node_map = {n.id: n for n in seeds}

        qualifying_nodes = [
            n
            for n in seeds
            if not n.is_immutable and tree.effective_degree(n.id) >= degree_threshold
        ]

        evt_disc_start = {
            "event": "reorg_discovery_started",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "evaluated_nodes_count": len(seeds),
            "qualifying_candidates_count": len(qualifying_nodes),
            "qualifying_node_titles": [n.title for n in qualifying_nodes],
            "message": (
                f"[{self.department_name}] Evaluating {len(seeds)} nodes "
                f"({len(qualifying_nodes)} mutable with degree >= {degree_threshold}) for reorganization..."
            ),
            "timestamp": time.time(),
        }
        emitted_events.append(evt_disc_start)

        # Early exit if no mutable nodes qualify for reorganization
        if not qualifying_nodes:
            disc_msg = (
                f"[{self.department_name}] Discovery completed: Sub-graph is cohesive. "
                f"No mutable nodes meet the degree threshold (>= {degree_threshold}) for subdivision."
            )
            evt_disc_done = {
                "event": "reorg_discovery_completed",
                "persona_id": self.department_id,
                "department_name": self.department_name,
                "candidate_count": 0,
                "candidate_ids": [],
                "message": disc_msg,
                "timestamp": time.time(),
            }
            emitted_events.append(evt_disc_done)
            return {"commands": [], "emitted_events": emitted_events}

        # STEP 1: Discovery Phase (Identify candidate mutable concept nodes)
        # Dedicated Concept Cache Map for Discovery candidates
        reorg_concept_mapper = PromptIdMapper(prefix="concept")
        nodes_payload = []
        for n in qualifying_nodes:
            c_idx = reorg_concept_mapper.register(n.id)
            nodes_payload.append(
                {
                    "candidate_index": c_idx,
                    "title": n.title,
                    "description": n.description,
                    "connection_degree": tree.effective_degree(n.id),
                    "connected_neighbor_context": [
                        {
                            "neighbor_title": nb["title"],
                            "direction": nb.get("direction", "incoming"),
                            "is_immutable": nb.get("is_immutable", False),
                        }
                        for nb in self._neighbor_entries_for_hub(n.id, project_id, tree)
                    ],
                }
            )

        system_discover = load_prompt(
            "graph_reorg_discover", department_name=self.department_name
        )
        user_discover = (
            "Candidate mutable concepts eligible for Subdivision "
            f"({len(qualifying_nodes)} candidate(s)):\n"
            f"{json_dumps_ingest(nodes_payload)}"
        )
        candidate_rationales: Dict[str, str] = {}
        try:
            payload_discover = llm_gateway.generate_structured_completion(
                [
                    {"role": "system", "content": system_discover},
                    {"role": "user", "content": user_discover},
                ],
                response_model=ReorgDiscoveryPayload,
                temperature=0.2,
                max_tokens=1024,
                max_retries=2,
                enable_reasoning=False,
                caller=f"GraphNavigator[{self.department_name}].reorg_discover",
            )
            # Decode integer candidate_index back to real string candidate_id
            for c in payload_discover.candidates:
                real_cid = reorg_concept_mapper.to_id(c.candidate_index)
                if real_cid and real_cid in node_map:
                    candidate_rationales[real_cid] = c.rationale
            candidate_ids = list(candidate_rationales.keys())
        except Exception as e:
            print(f"[{self.department_name}] Reorg discovery error: {e}")
            raise RuntimeError(
                f"[{self.department_name}] Concept reorganization discovery failed: {e}"
            ) from e

        if candidate_ids:
            found_titles = [
                (node_map.get(cid).title if node_map.get(cid) else cid)
                for cid in candidate_ids
            ]
            disc_msg = (
                f"[{self.department_name}] Discovered {len(candidate_ids)} over-clustered candidate node(s) "
                f"for subdivision: {', '.join(found_titles)}."
            )
        else:
            disc_msg = (
                f"[{self.department_name}] Discovery completed: Sub-graph is cohesive. "
                f"No nodes require intermediate subdivision."
            )

        evt_disc_done = {
            "event": "reorg_discovery_completed",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "candidate_count": len(candidate_ids),
            "candidate_ids": candidate_ids,
            "candidate_rationales": candidate_rationales,
            "message": disc_msg,
            "timestamp": time.time(),
        }
        emitted_events.append(evt_disc_done)

        work_queue = ReorgQueue()
        tree = MutableTreeIndex(project_id=project_id)
        for c_id in candidate_ids:
            work_queue.enqueue_discover_fifo(
                ReorgWorkItem(
                    hub_id=c_id,
                    kind="discover",
                    tree_parent_id=tree.parent_of(c_id),
                )
            )

        splits_executed, reorg_commands = self._process_reorg_queue(
            work_queue,
            project_id=project_id,
            degree_threshold=degree_threshold,
            doc_title=doc_title,
            proj_list=proj_list or [project_id],
            ingestion_engine=ingestion_engine,
            emitted_events=emitted_events,
            plan_only=plan_only,
            node_map=node_map,
            link_affected_ids=link_affected_ids,
        )

        tree = MutableTreeIndex(project_id=project_id)
        health = tree.health_metrics(k=settings.REACHABILITY_HOP_K)
        emitted_events.append(
            {
                "event": "graph_health_metrics",
                "metrics": health,
                "timestamp": time.time(),
            }
        )

        if plan_only:
            return {"commands": reorg_commands, "emitted_events": emitted_events}
        return {
            "emitted_events": emitted_events,
            "splits_executed": splits_executed,
        }

    def link_intradoc_concepts(
        self,
        intra_doc_nodes: List[GraphNode],
        doc_title: str,
        query: str,
        explored_nodes: List[GraphNode],
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Independent zero-consensus graph ingestion step.

        Emits commands (`CONNECT_DIRECT`, `CREATE_INTERMEDIATE`, `EDIT_CONCEPT` on mutable nodes,
        and `SPLIT_CONCEPT` on mutable nodes) to link extracted intra-document concepts to mutable tree nodes.
        """

        def _format_nodes(nodes: List[GraphNode]) -> List[Dict[str, Any]]:
            return [
                {
                    "id": n.id,
                    "title": n.title,
                    "description": n.description,
                    "node_type": n.node_type,
                    "immutable": n.is_immutable,
                    "passage_ids": n.passage_ids,
                }
                for n in nodes
            ]

        explored_payload = _format_nodes(explored_nodes)
        intra_payload = _format_nodes(intra_doc_nodes)

        prompt_str = f"""
        Genesis Project Scope:
        {self.genesis_node.description}

        Document Title: '{doc_title}'
        User Query: "{query}"

        Newly Extracted Intra-Document Concepts (IMMUTABLE, use these exact 'id' values when linking):
        {json.dumps(intra_payload, indent=2)}

        Explored Subgraph Nodes:
        {json.dumps(explored_payload, indent=2)}

        Emit independent linking and reorganization commands.
        """
        messages = [
            {
                "role": "system",
                "content": load_prompt(
                    "graph_link_intradoc", genesis_title=self.genesis_node.title
                ),
            }
        ]
        if chat_history:
            messages.extend(chat_history[-4:])
        messages.append({"role": "user", "content": prompt_str})

        try:
            payload_ingest = llm_gateway.generate_structured_completion(
                messages,
                response_model=PersonaIngestionCommandsPayload,
                temperature=0.2,
                max_tokens=4096,
                max_retries=2,
                enable_reasoning=False,
                caller=f"GraphNavigator[{self.department_name}].graph_link_intradoc",
            )
            raw_cmds = [c.model_dump() for c in payload_ingest.commands]
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "genesis_node_id": self.genesis_node.id,
                "traversed_node_ids": [n.id for n in explored_nodes],
                "subgraph_nodes": explored_nodes,
                "commands": raw_cmds,
            }
        except Exception as e:
            print(f"[{self.department_name}] Intra-doc linking error: {e}")
            raise RuntimeError(
                f"[{self.department_name}] Intra-document linking failed: {e}"
            ) from e
