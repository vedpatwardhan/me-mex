"""
Graph Navigator: Me-Mex v0.2

Genesis-rooted mutable tree traversal, intra-document linking, and selective reorganization.
"""

import json
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional
from app.db import db_engine
from app.config import settings
from app.models import (
    GraphNode,
    GraphEdge,
    ReorgDiscoveryPayload,
    ReorgSplitPayload,
    ReorgRewirePayload,
    PersonaIngestionCommandsPayload,
    PersonaExplorationPayload,
)
from app.services.graph_analytics import MutableTreeIndex, graph_analytics
from app.services.reorg_rewire_utils import finalize_rewire_edges
from app.services.llm_gateway import llm_gateway
from app.services.event_queue import event_queue
from app.services.prompt_mapper import PromptIdMapper
from app.prompts import load_prompt
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
                            "relation_desc": e.description,
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
                    "relation_desc": "SUBSET_OF",
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
                    "relation_desc": "RELEVANT_TO",
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
            query=query, chat_history=chat_history, project_id=project_id
        )

    def traverse_mutable_tree_from_genesis(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: Optional[str] = None,
        max_depth: Optional[int] = None,
        allow_web_search: bool = False,
    ) -> Dict[str, Any]:
        """Top-down traversal from Genesis over the mutable tree backbone."""
        pid = project_id or self.project_id
        max_traversal_depth = (
            max_depth if max_depth is not None else settings.MAX_TRAVERSAL_DEPTH
        )
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
        event_queue.push(pid, genesis_touch_evt)
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
{json.dumps(indexed_candidate_neighbors, indent=2)}"""
            messages = [
                {
                    "role": "system",
                    "content": load_prompt(
                        "graph_tree_traversal",
                        genesis_title=self.genesis_node.title,
                        max_depth=max_traversal_depth,
                    ),
                }
            ]
            if chat_history:
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
                    event_queue.push(pid, evt)
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
    ) -> Optional[Dict[str, Any]]:
        """Formulates intermediate sub-concepts (Step 2) and re-wires direct neighbor edges (Step 3)."""
        # Compute cardinality bounds for sub-concept formulation (n // 2 compression invariant)
        n_neighbors = len(target_neighbors_to_rewire)
        if n_neighbors <= 1:
            min_allowed_subs = 1
            max_allowed_subs = 1
        else:
            min_allowed_subs = 2
            max_allowed_subs = max(2, n_neighbors // 2)

        is_genesis = bool(
            target_node.metadata.get("is_genesis")
            or target_node.title.strip().lower() == "everything"
        )
        system_split = load_prompt(
            "graph_reorg_split",
            department_name=self.department_name,
            node_id=target_node.id,
            mode=mode,
            min_allowed_sub_concepts=min_allowed_subs,
            max_allowed_sub_concepts=max_allowed_subs,
            neighbor_count=n_neighbors,
            is_genesis=str(is_genesis).lower(),
        )

        # Concept Cache Map for target neighbors being rewired
        rewire_concept_mapper = PromptIdMapper(prefix="concept")
        indexed_neighbors_to_rewire = []
        for nb in target_neighbors_to_rewire:
            nb_idx = rewire_concept_mapper.register(nb["id"])
            entry = dict(nb)
            entry["neighbor_index"] = nb_idx
            # Exclude raw internal string id from user prompt to prevent model confusion
            entry.pop("id", None)
            indexed_neighbors_to_rewire.append(entry)

        split_context_parts = [
            f"Target over-clustered mutable concept: '{target_node.title}' (ID: {target_node.id})",
            f"Current Description: {target_node.description}",
            f"Reorganization Mode: {mode}",
            f"Target Neighbors to Move Outward ({len(indexed_neighbors_to_rewire)} items):",
            json.dumps(indexed_neighbors_to_rewire, indent=2),
        ]
        user_split = "\n\n".join(split_context_parts)

        try:
            payload_split = llm_gateway.generate_structured_completion(
                [
                    {"role": "system", "content": system_split},
                    {"role": "user", "content": user_split},
                ],
                response_model=ReorgSplitPayload,
                temperature=0.2,
                max_tokens=2048,
                max_retries=2,
                enable_reasoning=False,
                caller=f"GraphNavigator[{self.department_name}].reorg_split_{mode}",
            )
            formulated_subs = [s.model_dump() for s in payload_split.sub_concepts]
            # Programmatic compression guard: enforce max_allowed_subs ceiling
            if len(formulated_subs) > max_allowed_subs:
                print(
                    f"[{self.department_name}] Capping formulated sub-concepts from "
                    f"{len(formulated_subs)} to {max_allowed_subs} (n // 2 compression bound for {n_neighbors} neighbors)."
                )
                formulated_subs = formulated_subs[:max_allowed_subs]
        except Exception as e:
            print(
                f"[{self.department_name}] Step 2 Sub-concept formulation error for {target_node.id} (mode={mode}): {e}"
            )
            raise RuntimeError(
                f"[{self.department_name}] Step 2 Sub-concept formulation failed for {target_node.id} (mode={mode}): {e}"
            ) from e

        if not formulated_subs:
            return None

        split_event = {
            "event": "reorg_split_completed",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "node_id": target_node.id,
            "node_title": target_node.title,
            "reorg_mode": mode,
            "sub_concepts_count": len(formulated_subs),
            "sub_concepts": formulated_subs,
            "message": f"[{self.department_name}] Step 2 ({mode}) Completed: Formulated {len(formulated_subs)} sub-concepts for '{target_node.title}': {[s.get('title') for s in formulated_subs]}",
            "timestamp": time.time(),
        }
        emitted_events.append(split_event)
        event_queue.push(project_id, split_event)

        # Re-wiring step
        is_genesis_hub = bool(
            target_node.metadata.get("is_genesis")
            or target_node.title.strip().lower() == "everything"
        )
        tree_idx = MutableTreeIndex(project_id=project_id)
        parent = tree_idx.parent_of(target_node.id)
        ancestor_note = (
            "Leftovers use connect_to_sub_alias EVERYTHING (stay on Genesis)."
            if is_genesis_hub
            else f"Leftovers use connect_to_sub_alias ANCESTOR (rewire to parent '{parent}')."
        )
        system_rewire = load_prompt(
            "graph_reorg_rewire",
            department_name=self.department_name,
            node_id=target_node.id,
            mode=mode,
            is_genesis=str(is_genesis_hub).lower(),
        )
        user_rewire = f"""Target mutable concept: '{target_node.title}' (ID: {target_node.id})
Reorganization Mode: {mode}
{ancestor_note}

Formulated Sub-Concepts Available for Connection:
{json.dumps(formulated_subs, indent=2)}

Target Neighbors to Re-Wire ({len(indexed_neighbors_to_rewire)} items):
{json.dumps(indexed_neighbors_to_rewire, indent=2)}"""

        try:
            payload_rewire = llm_gateway.generate_structured_completion(
                [
                    {"role": "system", "content": system_rewire},
                    {"role": "user", "content": user_rewire},
                ],
                response_model=ReorgRewirePayload,
                temperature=0.2,
                max_tokens=4096,
                max_retries=2,
                enable_reasoning=False,
                caller=f"GraphNavigator[{self.department_name}].reorg_rewire_{mode}",
            )
            # Decode model integer neighbor_index back to real string neighbor_id
            rewired = []
            for r in payload_rewire.rewired_edges:
                real_nb_id = rewire_concept_mapper.to_id(r.neighbor_index)
                if real_nb_id:
                    rewired.append(
                        {
                            "neighbor_id": real_nb_id,
                            "connect_to_sub_alias": r.connect_to_sub_alias,
                            "relation_type": r.relation_type,
                            "description": r.description,
                        }
                    )
        except Exception as e:
            print(
                f"[{self.department_name}] Step 3 Neighbor edge re-wiring error for {target_node.id} (mode={mode}): {e}"
            )
            raise RuntimeError(
                f"[{self.department_name}] Step 3 Neighbor edge re-wiring failed for {target_node.id} (mode={mode}): {e}"
            ) from e

        partition_ids = [nb["id"] for nb in target_neighbors_to_rewire if nb.get("id")]
        rewired = finalize_rewire_edges(
            target_node.id,
            project_id,
            rewired,
            is_genesis_split=is_genesis_hub,
            explicit_neighbor_ids=partition_ids,
        )

        rewire_event = {
            "event": "reorg_rewire_completed",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "node_id": target_node.id,
            "node_title": target_node.title,
            "reorg_mode": mode,
            "rewired_edges_count": len(rewired),
            "rewired_edges": rewired,
            "message": f"[{self.department_name}] Step 3 ({mode}) Completed: Formulated {len(rewired)} re-wired edges for '{target_node.title}'.",
            "timestamp": time.time(),
        }
        emitted_events.append(rewire_event)
        event_queue.push(project_id, rewire_event)

        return {
            "parent_title": payload_split.parent_title,
            "parent_description": payload_split.parent_description,
            "sub_concepts": formulated_subs,
            "rewired_edges": rewired,
        }

    @staticmethod
    def _neighbor_entries_for_hub(
        hub_id: str, project_id: str, tree: MutableTreeIndex
    ) -> List[Dict[str, Any]]:
        """All direct neighbors of hub_id with metadata for partition prompts."""
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
            if not nb_id or nb_id in seen:
                continue
            parent_id = tree.parent_of(hub_id)
            if parent_id and nb_id == parent_id:
                desc = (e.description or "").upper()
                if "SUBSET" in desc:
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
                    "relation_to_target": e.description or "RELEVANT_TO",
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
        res = self._execute_split_and_rewire(
            target_node=target_node,
            mode="max_coverage",
            target_neighbors_to_rewire=neighbors,
            project_id=project_id,
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
        }

    def reorganize_overclustered_nodes(
        self,
        explored_nodes: list[GraphNode] | None = None,
        project_id: str = "global",
        degree_threshold: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Reorganization discover + max-coverage split for link-affected mutable hubs.

        Step 1: LLM discover among degree-qualified nodes from the provided seed set only.
        Step 2–3: Sub-concept formulation and neighbor rewire (wrapper at Genesis, replacement elsewhere).
        Orphan neighbors promote to tree parent or Everything; engine closes any LLM omissions.

        Returns {"commands": List[Dict], "emitted_events": List[Dict]}.
        """
        emitted_events: List[Dict[str, Any]] = []
        if not explored_nodes:
            return {"commands": [], "emitted_events": []}

        if degree_threshold is None:
            degree_threshold = settings.DEGREE_THRESHOLD

        tree = MutableTreeIndex(project_id=project_id)
        node_map = {n.id: n for n in explored_nodes}

        qualifying_nodes = [
            n
            for n in explored_nodes
            if not n.is_immutable and tree.effective_degree(n.id) >= degree_threshold
        ]

        evt_disc_start = {
            "event": "reorg_discovery_started",
            "persona_id": self.department_id,
            "department_name": self.department_name,
            "evaluated_nodes_count": len(explored_nodes),
            "qualifying_candidates_count": len(qualifying_nodes),
            "qualifying_node_titles": [n.title for n in qualifying_nodes],
            "message": (
                f"[{self.department_name}] Evaluating {len(explored_nodes)} nodes "
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
                            "relation": nb.get("relation_to_target", "RELEVANT_TO"),
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
            f"{json.dumps(nodes_payload, indent=2)}"
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

        reorg_commands: List[Dict[str, Any]] = []

        for c_id in candidate_ids:
            cmd = self.build_split_command_for_hub(
                c_id, project_id=project_id, emitted_events=emitted_events
            )
            if cmd:
                reorg_commands.append(cmd)
            else:
                target_node = node_map.get(c_id) or db_engine.get_node(c_id)
                title = target_node.title if target_node else c_id
                emitted_events.append(
                    {
                        "event": "reorg_candidate_skipped",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "concept_id": c_id,
                        "node_title": title,
                        "reason": "Partition returned no sub-concepts",
                        "message": f"[{self.department_name}] Skipped candidate '{title}': partition produced no split.",
                        "timestamp": time.time(),
                    }
                )

        health = tree.health_metrics(k=settings.REACHABILITY_HOP_K)
        emitted_events.append(
            {
                "event": "graph_health_metrics",
                "metrics": health,
                "timestamp": time.time(),
            }
        )
        return {"commands": reorg_commands, "emitted_events": emitted_events}

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
