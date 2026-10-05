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
        all_edges = db_engine.get_edges(project_id)
        adj_map: Dict[str, List[GraphEdge]] = defaultdict(list)
        for e in all_edges:
            adj_map[e.source_id].append(e)
            adj_map[e.target_id].append(e)

        visited_node_ids = set([self.hub_node.id])
        current_frontier = [self.hub_node.id]
        explored_nodes_map: Dict[str, GraphNode] = {self.hub_node.id: self.hub_node}

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

        for depth in range(1, max_depth + 1):
            if not current_frontier:
                break

            # Find all unvisited candidate neighbors connected to current frontier nodes
            candidate_neighbors: Dict[str, Dict[str, Any]] = {}
            for f_id in current_frontier:
                # Root Node Traversal Blocking: Root Nodes provide summary context, but block expanding further hops
                f_node = db_engine.get_node(f_id)
                if f_node and f_node.is_root_node:
                    continue

                for e in adj_map.get(f_id, []):
                    neighbor_id = e.target_id if e.source_id == f_id else e.source_id

                    # Filter by mutually exclusive partition if specified
                    if partition_node_ids and neighbor_id not in partition_node_ids:
                        continue

                    if (
                        neighbor_id not in visited_node_ids
                        and neighbor_id not in candidate_neighbors
                    ):
                        neighbor_node = db_engine.get_node(neighbor_id)
                        if neighbor_node:
                            candidate_neighbors[neighbor_id] = {
                                "id": neighbor_node.id,
                                "title": neighbor_node.title,
                                "body": neighbor_node.description,
                                "relation_desc": e.description,
                                "node_type": neighbor_node.node_type,
                            }

            if not candidate_neighbors:
                break

            # Evaluate candidate neighbors with persona LLM
            prompt_payload = f"""
            Concept Hub: '{self.hub_node.title}' (ID: {self.hub_node.id})
            User Query / Context: "{query}"
            Current Hop Level: {depth} / {max_depth}

            Candidate Unvisited Neighbor Concepts ({len(candidate_neighbors)} items):
            {json.dumps(list(candidate_neighbors.values()), indent=2)}

            Evaluate which neighbor concepts are relevant and worth exploring deeper for this query.
            """
            messages = [
                {
                    "role": "system",
                    "content": load_prompt("persona_subgraph_expansion").format(
                        hub_title=self.hub_node.title
                    ),
                }
            ]
            if chat_history:
                messages.extend(chat_history[-4:])
            messages.append({"role": "user", "content": prompt_payload})

            try:
                res = llm_gateway.generate_chat_completion(
                    messages,
                    temperature=0.2,
                    max_tokens=512,
                    response_format={"type": "json_object"},
                    enable_reasoning=False,
                )
                data = json.loads(res)
                selected_ids = data.get("selected_neighbor_ids", [])
                next_frontier = [
                    nid for nid in selected_ids if nid in candidate_neighbors
                ]
            except Exception as e:
                print(f"[{self.department_name}] Subgraph expansion error: {e}")
                next_frontier = list(candidate_neighbors.keys())[:2]

            for nid in next_frontier:
                visited_node_ids.add(nid)
                n_node = db_engine.get_node(nid)
                if n_node:
                    explored_nodes_map[nid] = n_node
                    # Emit real-time telemetry event
                    evt = {
                        "event": "node_touched",
                        "persona_id": self.department_id,
                        "persona_name": self.department_name,
                        "node_id": n_node.id,
                        "node_title": n_node.title,
                        "message": f"Concept '{n_node.title}' explored at hop {depth} by {self.department_name}.",
                        "timestamp": time.time(),
                    }
                    event_queue.push(project_id, evt)

            current_frontier = next_frontier

        self.last_explored_nodes = list(explored_nodes_map.values())
        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "hub_node_id": self.hub_node.id,
            "explored_nodes": self.last_explored_nodes,
            "traversed_node_ids": list(visited_node_ids),
        }

    def reorganize_concept_hub(
        self,
        project_id: str = "global",
        degree_threshold: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Independent Concept Node Reorganization & Splitting during Ingestion.

        Inspects mutable concept nodes in the persona's sub-graph. If a mutable node's connection degree
        exceeds `degree_threshold` (over-clustering), the persona inspects underlying passage chunks in `passages`
        and emits a `SPLIT_CONCEPT` command to restructure it into distinct sub-concepts.
        """
        all_edges = db_engine.get_edges(project_id)
        degree_map: Dict[str, int] = defaultdict(int)
        for e in all_edges:
            degree_map[e.source_id] += 1
            degree_map[e.target_id] += 1

        reorg_commands: List[Dict[str, Any]] = []

        for node in self.last_explored_nodes:
            # Skip immutable nodes (Root Nodes & Intra-Doc Concepts)
            if node.is_immutable:
                continue

            # Check if mutable concept node is over-clustered
            if degree_map.get(node.id, 0) >= degree_threshold:
                # Fetch plain-text passage chunks for ground-truth context
                passages = db_engine.get_passages_by_ids(node.passage_ids)
                passage_texts = [p.text_content for p in passages]

                prompt = f"""
                Over-Clustered Mutable Concept Node: '{node.title}' (ID: {node.id})
                Current Description: {node.description}
                Connection Degree: {degree_map[node.id]} links
                
                Associated Passage Text Chunks for Grounding:
                {json.dumps(passage_texts, indent=2)}

                Reorganize and split this concept node into 2 distinct focused sub-concepts.
                Return JSON format:
                {{
                  "action": "SPLIT_CONCEPT",
                  "concept_id": "{node.id}",
                  "sub_concepts": [
                    {{"title": "Focused Sub-Concept 1", "description": "...", "passage_ids": {json.dumps(node.passage_ids[:1])}}},
                    {{"title": "Focused Sub-Concept 2", "description": "...", "passage_ids": {json.dumps(node.passage_ids[1:])}}}
                  ]
                }}
                """
                messages = [
                    {
                        "role": "system",
                        "content": f"You are {self.department_name}. Reorganize over-clustered mutable concept nodes.",
                    },
                    {"role": "user", "content": prompt},
                ]
                try:
                    res = llm_gateway.generate_chat_completion(
                        messages,
                        temperature=0.2,
                        max_tokens=512,
                        response_format={"type": "json_object"},
                        enable_reasoning=False,
                    )
                    data = json.loads(res)
                    if data.get("action") == "SPLIT_CONCEPT":
                        reorg_commands.append(data)
                except Exception as e:
                    print(
                        f"[{self.department_name}] Concept reorg error for {node.id}: {e}"
                    )

        return reorg_commands

    def persona_ingestion(
        self,
        consolidated_concepts: List[Dict[str, Any]],
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

        prompt_str = f"""
        Concept Hub: '{self.hub_node.title}' (ID: {self.hub_node.id})
        Document Title: '{doc_title}'
        User Query: "{query}"

        Newly Extracted Intra-Document Concepts (IMMUTABLE):
        {json.dumps(consolidated_concepts, indent=2)}

        Explored Subgraph Nodes:
        {json.dumps(explored_payload, indent=2)}

        Emit independent linking and reorganization commands.
        """
        messages = [
            {
                "role": "system",
                "content": load_prompt("persona_ingestion").format(
                    hub_title=self.hub_node.title
                ),
            }
        ]
        if chat_history:
            messages.extend(chat_history[-4:])
        messages.append({"role": "user", "content": prompt_str})

        try:
            res = llm_gateway.generate_chat_completion(
                messages,
                temperature=0.2,
                max_tokens=1024,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            raw_cmds = data.get("commands", [])
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversed_node_ids": exploration.get("traversed_node_ids", []),
                "subgraph_nodes": explored_nodes,
                "commands": raw_cmds,
            }
        except Exception as e:
            print(f"[{self.department_name}] Persona ingestion error: {e}")
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversed_node_ids": exploration.get("traversed_node_ids", []),
                "subgraph_nodes": [],
                "commands": [],
            }
