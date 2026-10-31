"""
Specialist Persona Agent: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 4:
- Instantiated dynamically per concept hub partition detected by rustworkx unweighted eigenvector centrality.
- Conducts sub-graph exploration (`explore_concept_hub`) over mutually exclusive assigned partitions up to max_depth=3.
- Blocks expansion past Root Nodes (read summary for provenance only).
- Conducts independent passage-grounded concept node reorganization (`reorganize_concept_hub`) during Ingestion, splitting over-clustered mutable concept nodes (`SPLIT_CONCEPT`) using underlying text passage chunks.
- Operates zero-consensus independently (no objections or bilateral debate loops).
"""

import json
import time
from collections import defaultdict
from typing import List, Dict, Any, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
    ConceptHubCandidate,
    PersonaRouteRelevancePayload,
    ReorgDiscoveryPayload,
    ReorgSplitPayload,
    ReorgRewirePayload,
    PersonaIngestionCommandsPayload,
    PersonaExplorationPayload,
)
from app.services.llm_gateway import llm_gateway
from app.services.event_queue import event_queue
from app.services.prompt_mapper import PromptIdMapper
from app.prompts import load_prompt
from app.tools.search_tools import search_tools


class DepartmentPersonaAgent:
    """Specialized Persona Agent instantiated dynamically per concept hub partition."""

    def __init__(self, hub_node: GraphNode, score: float = 1.0):
        self.hub_node = hub_node
        self.score = score
        self.department_id = f"dept_{hub_node.id}"
        self.department_name = f"Persona Specialist: {hub_node.title}"
        self.last_explored_nodes: List[GraphNode] = [hub_node]

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

    def explore_concept_hub(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        allow_web_search: bool = False,
        project_id: str = "global",
        max_depth: int = 3,
        partition_node_ids: Optional[set] = None,
    ) -> Dict[str, Any]:
        """Multi-hop sub-graph exploration over mutually exclusive assigned partitions.

        Iteratively expands frontier nodes up to max_depth=3. Blocks further traversal past Root Nodes.
        Emits node_touched telemetry events to animate the visual canvas.
        """
        adj_map = self._get_adjacency_map(project_id)

        visited_node_ids = set([self.hub_node.id])
        current_frontier = [self.hub_node.id]
        explored_nodes_map: Dict[str, GraphNode] = {self.hub_node.id: self.hub_node}
        emitted_events: List[Dict[str, Any]] = []

        # Emit node_touched event for Hop 0 Hub Node
        hub_evt = {
            "event": "node_touched",
            "persona_id": self.department_id,
            "persona_name": self.department_name,
            "node_id": self.hub_node.id,
            "node_title": self.hub_node.title,
            "message": f"Concept '{self.hub_node.title}' touched by {self.department_name}.",
            "timestamp": time.time(),
        }
        event_queue.push(project_id, hub_evt)
        emitted_events.append(hub_evt)

        for depth in range(1, max_depth + 1):
            if not current_frontier:
                break

            # Find all unvisited candidate neighbors connected to current frontier nodes
            candidate_neighbors = self.get_candidate_neighbors(
                frontier_ids=current_frontier,
                adj_map=adj_map,
                visited_ids=visited_node_ids,
                partition_node_ids=partition_node_ids,
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

            prompt_payload = f"""Concept Hub: '{self.hub_node.title}' (ID: {self.hub_node.id})
User Query / Context: "{query}"
Current Hop Level: {depth} / {max_depth}

Candidate Unvisited Neighbor Concepts ({len(indexed_candidate_neighbors)} items):
{json.dumps(indexed_candidate_neighbors, indent=2)}"""
            messages = [
                {
                    "role": "system",
                    "content": load_prompt(
                        "persona_subgraph_expansion", hub_title=self.hub_node.title
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
                    caller=f"DepartmentPersonaAgent[{self.department_name}].subgraph_expansion",
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
                            f"Concept '{n_node.title}' explored at hop {depth}: {rationale}"
                            if rationale
                            else f"Concept '{n_node.title}' explored at hop {depth} by {self.department_name}."
                        ),
                        "timestamp": time.time(),
                    }
                    event_queue.push(project_id, evt)
                    emitted_events.append(evt)

            current_frontier = next_frontier

        self.last_explored_nodes = list(explored_nodes_map.values())
        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "hub_node_id": self.hub_node.id,
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
        negative_mutable_context: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Formulates intermediate sub-concepts (Step 2) and re-wires direct neighbor edges (Step 3)."""
        system_split = load_prompt(
            "persona_reorganize_split",
            department_name=self.department_name,
            node_id=target_node.id,
            mode=mode,
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
            f"Target Over-Clustered Concept Hub: '{target_node.title}' (ID: {target_node.id})",
            f"Current Description: {target_node.description}",
            f"Reorganization Mode: {mode}",
            f"Target Neighbors to Move Outward ({len(indexed_neighbors_to_rewire)} items):",
            json.dumps(indexed_neighbors_to_rewire, indent=2),
        ]
        if negative_mutable_context:
            indexed_negative_context = []
            for mut_nb in negative_mutable_context:
                mut_idx = rewire_concept_mapper.register(mut_nb["id"])
                mut_entry = dict(mut_nb)
                mut_entry["concept_index"] = mut_idx
                mut_entry.pop("id", None)
                indexed_negative_context.append(mut_entry)
            split_context_parts.extend(
                [
                    f"Existing Mutable Concepts (NEGATIVE CONTEXT - DO NOT DUPLICATE or REPHRASE, {len(indexed_negative_context)} items):",
                    json.dumps(indexed_negative_context, indent=2),
                ]
            )
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
                caller=f"DepartmentPersonaAgent[{self.department_name}].reorg_split_{mode}",
            )
            formulated_subs = [s.model_dump() for s in payload_split.sub_concepts]
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
        system_rewire = load_prompt(
            "persona_reorganize_rewire",
            department_name=self.department_name,
            node_id=target_node.id,
            mode=mode,
        )
        user_rewire = f"""Target Concept Hub: '{target_node.title}' (ID: {target_node.id})
Reorganization Mode: {mode}

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
                caller=f"DepartmentPersonaAgent[{self.department_name}].reorg_rewire_{mode}",
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
            "hub_title": payload_split.hub_title,
            "hub_description": payload_split.hub_description,
            "sub_concepts": formulated_subs,
            "rewired_edges": rewired,
        }

    def reorganize_concept_hub(
        self,
        explored_nodes: list[GraphNode] | None = None,
        project_id: str = "global",
        degree_threshold: int = 5,
    ) -> Dict[str, Any]:
        """
        3-Step Non-Destructive Concept Node Reorganization & Subdivision during Ingestion.

        Step 1 (Discovery): Inspects full sub-graph payload to discover candidate over-clustered mutable concept nodes.
        Step 2 (Formulation): Formulates 2-3 focused sub-concepts around each target node using passage text grounding.
        Step 3 (Neighbor Re-Wiring): Re-wires direct neighbor edges to connect through the new sub-concepts while preserving the original concept hub as an umbrella node.

        Returns a dictionary containing both executable commands and emitted telemetry events:
        {"commands": List[Dict[str, Any]], "emitted_events": List[Dict[str, Any]]}
        """
        emitted_events: List[Dict[str, Any]] = []
        if not explored_nodes:
            return {"commands": [], "emitted_events": []}

        all_edges = db_engine.get_edges(project_id)
        node_id_set = {n.id for n in explored_nodes}
        node_map = {n.id: n for n in explored_nodes}

        # Filter edges active within the explored sub-graph partition
        subgraph_edges = [
            e
            for e in all_edges
            if e.source_id in node_id_set or e.target_id in node_id_set
        ]

        degree_map: Dict[str, int] = defaultdict(int)
        neighbor_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        def _make_neighbor(n_id: str, direction: str, rel_type: str) -> Dict[str, Any]:
            n_node = db_engine.get_node(n_id)
            return {
                "neighbor_id": n_id,
                "neighbor_title": n_node.title if n_node else n_id,
                "direction": direction,
                "relation_type": rel_type,
            }

        for e in subgraph_edges:
            degree_map[e.source_id] += 1
            degree_map[e.target_id] += 1

            if e.source_id in node_id_set:
                neighbor_map[e.source_id].append(
                    _make_neighbor(e.target_id, "outgoing", e.description)
                )
            if e.target_id in node_id_set:
                neighbor_map[e.target_id].append(
                    _make_neighbor(e.source_id, "incoming", e.description)
                )

        # Count mutable candidate nodes meeting the degree threshold
        qualifying_nodes = [
            n
            for n in explored_nodes
            if not n.is_immutable and degree_map.get(n.id, 0) >= degree_threshold
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
                    "connection_degree": degree_map.get(n.id, 0),
                    "connected_neighbor_context": [
                        {
                            "neighbor_title": nb["neighbor_title"],
                            "relation": nb["relation_type"],
                            "direction": nb["direction"],
                        }
                        for nb in neighbor_map.get(n.id, [])
                    ],
                }
            )

        system_discover = load_prompt(
            "persona_reorganize_discover", department_name=self.department_name
        )
        user_discover = (
            "Candidate Mutable Concept Hubs Eligible for Subdivision "
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
                caller=f"DepartmentPersonaAgent[{self.department_name}].reorg_discover",
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

        # STEPS 2 & 3: Separated Sub-Concept Formulation & Neighbor Edge Re-Wiring per candidate concept node
        for c_id in candidate_ids:
            target_node = node_map.get(c_id) or db_engine.get_node(c_id)
            if not target_node:
                skip_evt = {
                    "event": "reorg_candidate_skipped",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "concept_id": c_id,
                    "reason": "Node not found in graph",
                    "message": f"[{self.department_name}] Skipped candidate '{c_id}': not found in graph.",
                    "timestamp": time.time(),
                }
                emitted_events.append(skip_evt)
                continue

            if target_node.is_immutable:
                skip_evt = {
                    "event": "reorg_candidate_skipped",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "concept_id": c_id,
                    "node_title": target_node.title,
                    "reason": "Node is immutable (Root or intra-document concept)",
                    "message": f"[{self.department_name}] Skipped candidate '{target_node.title}': immutable node.",
                    "timestamp": time.time(),
                }
                emitted_events.append(skip_evt)
                continue

            neighbors = neighbor_map.get(c_id, [])

            # Classify direct neighbors into immutable evidence concepts and mutable concepts
            immutable_evidence_concepts = []
            mutable_concepts = []
            for nb in neighbors:
                nb_id = nb.get("neighbor_id")
                nb_node = (
                    (node_map.get(nb_id) or db_engine.get_node(nb_id))
                    if nb_id
                    else None
                )
                if nb_node:
                    entry = {
                        "id": nb_node.id,
                        "title": nb_node.title,
                        "description": nb_node.description,
                        "is_immutable": nb_node.is_immutable,
                        "node_type": nb_node.node_type,
                        "relation_to_hub": nb.get("relation_type", "RELEVANT_TO"),
                        "direction": nb.get("direction", "incoming"),
                    }
                    if nb_node.is_immutable:
                        immutable_evidence_concepts.append(entry)
                    else:
                        mutable_concepts.append(entry)

            total_neighbors = len(immutable_evidence_concepts) + len(mutable_concepts)
            if total_neighbors == 0:
                continue

            # STEP 2 & 3: Immutable-First Neighborhood Routing
            # 1. If any immutable leaves exist (|N_imm| > 0):
            #    - Purely Immutable (|N_mut| == 0): Direct outward leaf clustering.
            #    - Mixed (|N_mut| > 0): Phase 2a (Leaf Outward Movement with negative mutable context).
            #      After rewiring, re-evaluate post-2a degree. If still >= threshold, the hub's mutable
            #      neighborhood is updated so it naturally flows into the mutable split below.
            if immutable_evidence_concepts:
                mode = "pure_immutable" if not mutable_concepts else "leaf_outward"
                phase_2a_res = self._execute_split_and_rewire(
                    target_node=target_node,
                    mode=mode,
                    target_neighbors_to_rewire=immutable_evidence_concepts,
                    project_id=project_id,
                    emitted_events=emitted_events,
                    negative_mutable_context=mutable_concepts
                    if mutable_concepts
                    else None,
                )
                if not phase_2a_res:
                    skip_evt = {
                        "event": "reorg_candidate_skipped",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "concept_id": c_id,
                        "node_title": target_node.title,
                        "reason": f"Sub-concept formulation returned 0 concepts ({mode})",
                        "message": f"[{self.department_name}] Skipped candidate '{target_node.title}': {mode} produced 0 sub-concepts.",
                        "timestamp": time.time(),
                    }
                    emitted_events.append(skip_evt)
                    continue

                reorg_commands.append(
                    {
                        "action": "SPLIT_CONCEPT",
                        "concept_id": target_node.id,
                        "hub_title": phase_2a_res["hub_title"],
                        "hub_description": phase_2a_res["hub_description"],
                        "sub_concepts": phase_2a_res["sub_concepts"],
                        "rewired_edges": phase_2a_res["rewired_edges"],
                    }
                )

                # If there were no mutable concepts, reorganization for this hub is complete.
                if not mutable_concepts:
                    continue

                # In mixed mode: dynamically re-evaluate degree after leaf absorption.
                post_2a_degree = len(mutable_concepts) + len(
                    phase_2a_res["sub_concepts"]
                )
                if post_2a_degree < degree_threshold:
                    decongest_evt = {
                        "event": "reorg_hub_decongested",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "node_id": target_node.id,
                        "node_title": target_node.title,
                        "pre_degree": total_neighbors,
                        "post_2a_degree": post_2a_degree,
                        "threshold": degree_threshold,
                        "message": (
                            f"[{self.department_name}] Hub '{target_node.title}' successfully decongested "
                            f"(degree: {total_neighbors} -> {post_2a_degree} < threshold {degree_threshold}). "
                            f"Phase 2b skipped."
                        ),
                        "timestamp": time.time(),
                    }
                    emitted_events.append(decongest_evt)
                    event_queue.push(project_id, decongest_evt)
                    continue

                # Hub remains over-clustered: absorb the newly created sub-concepts into the mutable set
                # and fall through directly into the mutable split logic.
                new_sub_nodes = [
                    {
                        "id": f"sub_{s.get('sub_id_alias', idx)}",
                        "title": s.get("title"),
                        "description": s.get("description"),
                        "is_immutable": False,
                        "node_type": "CONCEPT",
                        "relation_to_hub": "SUBSET_OF",
                        "direction": "incoming",
                    }
                    for idx, s in enumerate(phase_2a_res["sub_concepts"])
                ]
                mutable_concepts = mutable_concepts + new_sub_nodes

            # 2. Purely Mutable Outward Split:
            # Handles either:
            # - Hubs that originally had ONLY mutable neighbors (|N_imm| == 0, Scenario B)
            # - Mixed hubs where post-2a degree was still >= threshold (Phase 2b of Scenario C)
            if mutable_concepts:
                mut_res = self._execute_split_and_rewire(
                    target_node=target_node,
                    mode="mutable_partition",
                    target_neighbors_to_rewire=mutable_concepts,
                    project_id=project_id,
                    emitted_events=emitted_events,
                )
                if mut_res:
                    reorg_commands.append(
                        {
                            "action": "SPLIT_CONCEPT",
                            "concept_id": target_node.id,
                            "hub_title": mut_res["hub_title"],
                            "hub_description": mut_res["hub_description"],
                            "sub_concepts": mut_res["sub_concepts"],
                            "rewired_edges": mut_res["rewired_edges"],
                        }
                    )
                else:
                    skip_evt = {
                        "event": "reorg_candidate_skipped",
                        "persona_id": self.department_id,
                        "department_name": self.department_name,
                        "concept_id": c_id,
                        "node_title": target_node.title,
                        "reason": "Mutable sub-concept formulation returned 0 concepts",
                        "message": f"[{self.department_name}] Skipped candidate '{target_node.title}': mutable partition produced 0 sub-concepts.",
                        "timestamp": time.time(),
                    }
                    emitted_events.append(skip_evt)

        return {"commands": reorg_commands, "emitted_events": emitted_events}

    def persona_ingestion(
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
        and `SPLIT_CONCEPT` on mutable nodes) to link extracted intra-document concepts to domain hubs.
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
        Concept Hub: '{self.hub_node.title}' (ID: {self.hub_node.id})
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
                    "persona_ingestion", hub_title=self.hub_node.title
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
                caller=f"DepartmentPersonaAgent[{self.department_name}].persona_ingestion",
            )
            raw_cmds = [c.model_dump() for c in payload_ingest.commands]
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversed_node_ids": [n.id for n in explored_nodes],
                "subgraph_nodes": explored_nodes,
                "commands": raw_cmds,
            }
        except Exception as e:
            print(f"[{self.department_name}] Persona ingestion error: {e}")
            raise RuntimeError(
                f"[{self.department_name}] Persona cross-linking ingestion failed: {e}"
            ) from e

    @classmethod
    def get_hub_preview_subconcepts(
        cls,
        hub_id: str,
        adj_map: Dict[str, List[GraphEdge]],
        max_depth: int = 2,
        max_items: int = 15,
    ) -> List[Dict[str, Any]]:
        """Collects a preview of sub-concepts connected to a hub up to max_depth using common neighbor exploration."""
        visited_sub_ids = {hub_id}
        frontier = [hub_id]
        depth_subconcepts = []

        for cur_depth in range(1, max_depth + 1):
            candidates = cls.get_candidate_neighbors(
                frontier_ids=frontier,
                adj_map=adj_map,
                visited_ids=visited_sub_ids,
            )
            if not candidates:
                break

            frontier = []
            for n_id, n_data in candidates.items():
                visited_sub_ids.add(n_id)
                frontier.append(n_id)
                depth_subconcepts.append(
                    {
                        "title": n_data["title"],
                        "depth": cur_depth,
                        "relation": n_data["relation_desc"],
                    }
                )
                if len(depth_subconcepts) >= max_items:
                    break
            if len(depth_subconcepts) >= max_items:
                break

        return depth_subconcepts

    @staticmethod
    def filter_relevant_hubs(
        doc_title: str,
        intra_doc_nodes: List[GraphNode],
        candidate_hubs: List[GraphNode],
        project_id: str = "global",
        preview_depth: int = 2,
    ) -> List[str]:
        """Pre-check relevance filtering evaluating candidate persona hubs against
        extracted concepts.

        Enriches candidate hubs with depth-2 sub-concepts for enhanced semantic
        resolution.
        Selects 1 to 3 candidate hubs that have genuine domain relevance.
        Guarantees fallback to the 'Everything' hub if no specialized domain hub fits.
        """
        adj_map = DepartmentPersonaAgent._get_adjacency_map(project_id)

        # Concept Cache Map for routing: candidate hubs and intra-doc concepts
        concept_mapper = PromptIdMapper(prefix="concept")

        candidate_hubs_payload = []
        for h in candidate_hubs:
            hub_index = concept_mapper.register(h.id)
            depth_subconcepts = DepartmentPersonaAgent.get_hub_preview_subconcepts(
                hub_id=h.id,
                adj_map=adj_map,
                max_depth=preview_depth,
                max_items=15,
            )
            hub_dict = {
                "hub_index": hub_index,
                "title": h.title,
                "description": h.description,
            }
            if depth_subconcepts:
                hub_dict["connected_subconcepts"] = depth_subconcepts
            candidate_hubs_payload.append(hub_dict)

        intra_concepts_payload = []
        for n in intra_doc_nodes:
            c_idx = concept_mapper.register(n.id)
            intra_concepts_payload.append(
                {"concept_index": c_idx, "title": n.title, "description": n.description}
            )

        system_route = load_prompt("persona_route_relevance")
        user_route = f"""Incoming Document: '{doc_title}'
Newly Extracted Concepts ({len(intra_concepts_payload)} items):
{json.dumps(intra_concepts_payload, indent=2)}

Candidate Persona Domain Hubs with Local Sub-Concepts ({len(candidate_hubs_payload)} items):
{json.dumps(candidate_hubs_payload, indent=2)}"""
        selected_hub_ids = []
        try:
            payload_route = llm_gateway.generate_structured_completion(
                [
                    {"role": "system", "content": system_route},
                    {"role": "user", "content": user_route},
                ],
                response_model=PersonaRouteRelevancePayload,
                temperature=0.1,
                max_tokens=512,
                max_retries=2,
                enable_reasoning=False,
                caller="DepartmentPersonaAgent.filter_relevant_hubs",
            )
            # Decode returned integer hub indices back to string hub IDs
            selected_hub_ids = [
                concept_mapper.to_id(h_idx)
                for h_idx in payload_route.selected_hub_indices
                if concept_mapper.to_id(h_idx) is not None
            ]
        except Exception as e:
            print(f"[DepartmentPersonaAgent] Persona relevance routing error: {e}")
            selected_hub_ids = []

        # Enforce universal fallback: if empty or unselected, fallback to 'Everything'
        if not selected_hub_ids:
            genesis_candidate = db_engine.get_genesis_node(project_id)
            selected_hub_ids = [genesis_candidate.id]

        return selected_hub_ids
