import json
from typing import List, Dict, Any, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
)
from app.services.llm_gateway import llm_gateway
from app.prompts import load_prompt
from app.tools.search_tools import search_tools


class DepartmentPersonaAgent:
    """Specialized Persona Agent instantiated dynamically per concept hub."""

    def __init__(self, hub_node: GraphNode, score: float = 1.0):
        self.hub_node = hub_node
        self.score = score
        self.department_id = f"dept_{hub_node.id}"
        self.department_name = f"Persona Specialist: {hub_node.title}"

    def explore_concept_hub(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        allow_web_search: bool = False,
        project_id: str = "global",
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """Multi-hop sub-graph exploration common to retrieval and ingestion.

        Iteratively expands frontier nodes up to max_depth, asking the persona LLM to evaluate candidate
        neighbors at each hop to build a rich multi-hop domain context.
        """
        all_edges = db_engine.get_edges(project_id)

        visited_node_ids = set([self.hub_node.id])
        current_frontier = [self.hub_node.id]
        explored_nodes_map: Dict[str, GraphNode] = {self.hub_node.id: self.hub_node}

        for depth in range(1, max_depth + 1):
            if not current_frontier:
                break

            # Find all unvisited candidate neighbors connected to current frontier nodes
            candidate_neighbors: Dict[str, Dict[str, Any]] = {}
            for e in all_edges:
                connected_id = None
                if (
                    e.source_id in current_frontier
                    and e.target_id not in visited_node_ids
                ):
                    connected_id = e.target_id
                elif (
                    e.target_id in current_frontier
                    and e.source_id not in visited_node_ids
                ):
                    connected_id = e.source_id

                if connected_id and connected_id not in candidate_neighbors:
                    neighbor_node = db_engine.get_node(connected_id)
                    if neighbor_node:
                        candidate_neighbors[connected_id] = {
                            "id": neighbor_node.id,
                            "title": neighbor_node.title,
                            "body": neighbor_node.text_body[:200],
                            "relation_desc": e.text_body,
                        }

            if not candidate_neighbors:
                break

            # If small candidate set (<= 3), auto-expand; otherwise ask persona to select relevant neighbors
            next_frontier = []
            if len(candidate_neighbors) <= 3:
                next_frontier = list(candidate_neighbors.keys())
            else:
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
                    print(
                        f"[{self.department_name}] Hop {depth} expansion error ({e}); selecting top 3 candidates."
                    )
                    next_frontier = list(candidate_neighbors.keys())[:3]

            if not next_frontier:
                break

            for nid in next_frontier:
                visited_node_ids.add(nid)
                node_obj = db_engine.get_node(nid)
                if node_obj:
                    explored_nodes_map[nid] = node_obj

            # Filter next_frontier to ONLY concept nodes (blocking root media nodes from expanding further hops)
            current_frontier = [
                nid
                for nid in next_frontier
                if explored_nodes_map.get(nid)
                and explored_nodes_map[nid].node_type == "concept"
            ]

        traversed_node_ids = list(visited_node_ids)
        subgraph_nodes = list(explored_nodes_map.values())

        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "hub_node_id": self.hub_node.id,
            "hub_title": self.hub_node.title,
            "traversing_node_ids": traversed_node_ids,
            "subgraph_nodes": subgraph_nodes,
        }

    def explore_and_retrieve(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        allow_web_search: bool = False,
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Retrieval mode: runs concept hub exploration, then synthesizes persona perspective."""
        exploration = self.explore_concept_hub(
            query=query,
            chat_history=chat_history,
            allow_web_search=False,
            project_id=project_id,
        )

        subgraph_nodes = exploration.get("subgraph_nodes", [])

        # Synthesize persona perspective over accumulated multi-hop sub-graph
        prompt_payload = f"""
        You are the Specialist Agent for Concept Hub '{self.hub_node.title}'.
        Your Hub Concept Node Details:
        - Title: {self.hub_node.title}
        - Description: {self.hub_node.text_body}

        Explored Multi-Hop Subgraph Concepts ({len(subgraph_nodes)} nodes):
        {json.dumps([{"id": n.id, "title": n.title, "body": n.text_body[:200]} for n in subgraph_nodes])}

        Task / User Query: "{query}"

        Analyze the task from your concept hub perspective using your deep multi-hop graph context. Debate the relevance of your domain knowledge to the prompt and provide expert observations.
        """
        messages = [
            {
                "role": "system",
                "content": load_prompt("department_persona").format(
                    hub_title=self.hub_node.title
                ),
            }
        ]
        if chat_history:
            messages.extend(chat_history[-4:])
        messages.append({"role": "user", "content": prompt_payload})

        llm_response = llm_gateway.generate_chat_completion(messages)

        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "hub_node_id": self.hub_node.id,
            "hub_title": self.hub_node.title,
            "traversing_node_ids": exploration.get("traversing_node_ids", []),
            "subgraph_nodes": subgraph_nodes,
            "perspective": llm_response,
            "web_search_used": False,
        }

    def persona_ingestion(
        self,
        consolidated_concepts: List[Dict[str, Any]],
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Ingestion mode: Executes shared exploration first, then outputs a structured command list for graph integration."""
        exploration = self.explore_concept_hub(
            query=query,
            chat_history=chat_history,
            allow_web_search=False,
            project_id=project_id,
        )

        subgraph_nodes = exploration.get("subgraph_nodes", [])

        prompt_payload = (
            f"Document Title: {doc_title}\n"
            f"User Query Context: {query}\n\n"
            f"Hub Concept: '{self.hub_node.title}' (ID: {self.hub_node.id})\n"
            f"Hub Description: {self.hub_node.text_body}\n\n"
            f"Explored Subgraph Concepts ({len(subgraph_nodes)} nodes):\n"
            f"{json.dumps([{'id': n.id, 'title': n.title, 'body': n.text_body[:200]} for n in subgraph_nodes], indent=2)}\n\n"
            f"Candidate Intra-Document Concepts ({len(consolidated_concepts)} items):\n"
            f"{json.dumps(consolidated_concepts, indent=2)}"
        )

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
        messages.append({"role": "user", "content": prompt_payload})

        try:
            res = llm_gateway.generate_chat_completion(
                messages,
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            commands = data.get("commands", [])
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversing_node_ids": exploration.get("traversing_node_ids", []),
                "commands": commands,
            }
        except Exception as e:
            print(f"[{self.department_name}] Persona ingestion error: {e}")
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversing_node_ids": exploration.get("traversing_node_ids", []),
                "commands": [],
            }
