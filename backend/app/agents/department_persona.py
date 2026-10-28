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
            prompt_payload = f"""Concept Hub: '{self.hub_node.title}' (ID: {self.hub_node.id})
User Query / Context: "{query}"
Current Hop Level: {depth} / {max_depth}

Candidate Unvisited Neighbor Concepts ({len(candidate_neighbors)} items):
{json.dumps(list(candidate_neighbors.values()), indent=2)}"""
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
                # Map neighbor ID to its specific rationale
                neighbor_rationales: Dict[str, str] = {}
                if payload.selected_neighbors:
                    for item in payload.selected_neighbors:
                        if item.node_id in candidate_neighbors:
                            neighbor_rationales[item.node_id] = item.rationale
                elif payload.selected_neighbor_ids:
                    for nid in payload.selected_neighbor_ids:
                        if nid in candidate_neighbors:
                            neighbor_rationales[
                                nid
                            ] = "Relevant domain concept selected for exploration."

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
        print(
            f"[{self.department_name}] Step 3 Reorganization started: {evt_disc_start['message']}"
        )

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
            print(disc_msg)
            return {"commands": [], "emitted_events": emitted_events}

        # STEP 1: Discovery Phase (Identify candidate mutable concept nodes)
        # Only present valid qualifying mutable nodes as candidates to prevent LLM picking immutable neighbor IDs
        nodes_payload = [
            {
                "candidate_id": n.id,
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
            for n in qualifying_nodes
        ]

        system_discover = load_prompt(
            "persona_reorganize_discover", department_name=self.department_name
        )
        user_discover = f"""Candidate Mutable Concept Hubs Eligible for Subdivision ({len(qualifying_nodes)} candidate(s)):
{json.dumps(nodes_payload, indent=2)}"""
        candidate_ids = []
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
            candidate_ids = payload_discover.candidate_concept_ids
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
            "message": disc_msg,
            "timestamp": time.time(),
        }
        emitted_events.append(evt_disc_done)
        print(disc_msg)

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
                print(skip_evt["message"])
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
                print(skip_evt["message"])
                continue

            neighbors = neighbor_map.get(c_id, [])

            # STEP 2: Pure Semantic Sub-Concept Formulation
            # Invariant: Sub-concept formulation operates purely on the rich titles, descriptions,
            # and relations of connected neighbor concepts without leaking verbose raw passage texts.
            immutable_evidence_concepts = []
            existing_domain_hubs = []
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
                        existing_domain_hubs.append(entry)

            system_split = load_prompt(
                "persona_reorganize_split",
                department_name=self.department_name,
                node_id=target_node.id,
            )
            user_split = f"""Target Over-Clustered Mutable Concept Hub: '{target_node.title}' (ID: {target_node.id})
Current Description: {target_node.description}
Total Connected Neighbor Concepts: {len(immutable_evidence_concepts) + len(existing_domain_hubs)}

[PRIORITY 1: Newly Attached Immutable Concepts ({len(immutable_evidence_concepts)} items)]:
{json.dumps(immutable_evidence_concepts, indent=2)}

[PRIORITY 2: Existing Mutable Domain Hubs ({len(existing_domain_hubs)} items)]:
{json.dumps(existing_domain_hubs, indent=2)}"""
            sub_concepts = []
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
                    caller=f"DepartmentPersonaAgent[{self.department_name}].reorg_split",
                )
                sub_concepts = [s.model_dump() for s in payload_split.sub_concepts]
            except Exception as e:
                print(
                    f"[{self.department_name}] Step 2 Sub-concept formulation error for {target_node.id}: {e}"
                )
                raise RuntimeError(
                    f"[{self.department_name}] Step 2 Sub-concept formulation failed for {target_node.id}: {e}"
                ) from e

            if not sub_concepts:
                skip_evt = {
                    "event": "reorg_candidate_skipped",
                    "persona_id": self.department_id,
                    "department_name": self.department_name,
                    "concept_id": c_id,
                    "node_title": target_node.title,
                    "reason": "Sub-concept formulation returned 0 concepts",
                    "message": f"[{self.department_name}] Skipped candidate '{target_node.title}': formulation produced 0 sub-concepts.",
                    "timestamp": time.time(),
                }
                emitted_events.append(skip_evt)
                print(skip_evt["message"])
                continue

            # Emit split formulation completed event
            split_evt = {
                "event": "reorg_split_completed",
                "persona_id": self.department_id,
                "department_name": self.department_name,
                "node_id": target_node.id,
                "node_title": target_node.title,
                "sub_concepts_count": len(sub_concepts),
                "sub_concepts": sub_concepts,
                "message": f"[{self.department_name}] Step 2 Completed: Formulated {len(sub_concepts)} sub-concepts for '{target_node.title}': {[s.get('title') for s in sub_concepts]}",
                "timestamp": time.time(),
            }
            emitted_events.append(split_evt)
            event_queue.push(project_id, split_evt)
            print(split_evt["message"])

            # STEP 3: Neighbor Edge Re-Wiring (Iterate over ALL direct neighbors)
            system_rewire = load_prompt(
                "persona_reorganize_rewire",
                department_name=self.department_name,
                node_id=target_node.id,
            )
            user_rewire = f"""Target Concept Hub: '{target_node.title}' (ID: {target_node.id})

Formulated Sub-Concepts Available for Connection:
{json.dumps(sub_concepts, indent=2)}

Complete List of Direct Neighbor Nodes to Re-Wire:
[Newly Attached Immutable Concepts ({len(immutable_evidence_concepts)})]:
{json.dumps(immutable_evidence_concepts, indent=2)}

[Existing Mutable Domain Hubs ({len(existing_domain_hubs)})]:
{json.dumps(existing_domain_hubs, indent=2)}"""
            rewired_edges = []
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
                    caller=f"DepartmentPersonaAgent[{self.department_name}].reorg_rewire",
                )
                rewired_edges = [r.model_dump() for r in payload_rewire.rewired_edges]
            except Exception as e:
                print(
                    f"[{self.department_name}] Step 3 Neighbor edge re-wiring error for {target_node.id}: {e}"
                )
                raise RuntimeError(
                    f"[{self.department_name}] Step 3 Neighbor edge re-wiring failed for {target_node.id}: {e}"
                ) from e

            # Emit rewiring completed event
            rewire_evt = {
                "event": "reorg_rewire_completed",
                "persona_id": self.department_id,
                "department_name": self.department_name,
                "node_id": target_node.id,
                "node_title": target_node.title,
                "rewired_edges_count": len(rewired_edges),
                "rewired_edges": rewired_edges,
                "message": f"[{self.department_name}] Step 3 Completed: Formulated {len(rewired_edges)} re-wired edge assignments for '{target_node.title}'.",
                "timestamp": time.time(),
            }
            emitted_events.append(rewire_evt)
            event_queue.push(project_id, rewire_evt)
            print(rewire_evt["message"])

            reorg_commands.append(
                {
                    "action": "SPLIT_CONCEPT",
                    "concept_id": target_node.id,
                    "sub_concepts": sub_concepts,
                    "rewired_edges": rewired_edges,
                }
            )

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

        candidate_hubs_payload = []
        for h in candidate_hubs:
            depth_subconcepts = DepartmentPersonaAgent.get_hub_preview_subconcepts(
                hub_id=h.id,
                adj_map=adj_map,
                max_depth=preview_depth,
                max_items=15,
            )
            hub_dict = {
                "id": h.id,
                "title": h.title,
                "description": h.description,
            }
            if depth_subconcepts:
                hub_dict["connected_subconcepts"] = depth_subconcepts
            candidate_hubs_payload.append(hub_dict)

        intra_concepts_payload = [
            {"id": n.id, "title": n.title, "description": n.description}
            for n in intra_doc_nodes
        ]

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
            selected_hub_ids = payload_route.selected_hub_ids
        except Exception as e:
            print(f"[DepartmentPersonaAgent] Persona relevance routing error: {e}")
            selected_hub_ids = []

        # Enforce universal fallback: if empty or unselected, fallback to 'Everything' or first top hub
        if not selected_hub_ids:
            genesis_candidate = next(
                (
                    h.id
                    for h in candidate_hubs
                    if h.title.strip().lower() == "everything"
                ),
                candidate_hubs[0].id if candidate_hubs else None,
            )
            if genesis_candidate:
                selected_hub_ids = [genesis_candidate]

        return selected_hub_ids
