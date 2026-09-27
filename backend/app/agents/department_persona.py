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

    def explore_and_debate_hub(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        allow_web_search: bool = True,
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Shared sub-graph exploration, web search, and hub relevance debate common to retrieval and ingestion."""
        all_edges = db_engine.get_edges(project_id)
        adjacent_edges = [
            e
            for e in all_edges
            if e.source_id == self.hub_node.id or e.target_id == self.hub_node.id
        ]
        adjacent_node_ids = set([self.hub_node.id])
        for e in adjacent_edges:
            adjacent_node_ids.add(e.source_id)
            adjacent_node_ids.add(e.target_id)

        traversed_node_ids = list(adjacent_node_ids)
        subgraph_nodes = [
            db_engine.get_node(nid)
            for nid in traversed_node_ids
            if db_engine.get_node(nid)
        ]

        # Web Search Context Supplementation via DuckDuckGo tool if allowed
        web_search_results = ""
        if allow_web_search and any(
            k in query.lower()
            for k in ["search", "latest", "recent", "what is", "web", "news"]
        ):
            try:
                web_res = search_tools.search_duckduckgo(
                    f"{self.hub_node.title} {query}"
                )
                web_search_results = (
                    f"\nDuckDuckGo Live Web Context:\n{json.dumps(web_res[:2])}"
                )
            except Exception as e:
                web_search_results = f"\nWeb search attempt: {e}"

        prompt_payload = f"""
        You are the Specialist Agent for Concept Hub '{self.hub_node.title}'.
        Your Hub Concept Node Details:
        - Title: {self.hub_node.title}
        - Description: {self.hub_node.text_body}

        Adjacent Subgraph Concepts:
        {json.dumps([{"id": n.id, "title": n.title, "body": n.text_body[:200]} for n in subgraph_nodes])}
        {web_search_results}

        Task / User Query: "{query}"

        Analyze the task from your concept hub perspective. Debate the relevance of your domain knowledge to the prompt and provide expert observations.
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
            "traversing_node_ids": traversed_node_ids,
            "subgraph_nodes": subgraph_nodes,
            "perspective": llm_response,
            "web_search_used": bool(web_search_results),
        }

    def explore_and_debate_retrieval(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        allow_web_search: bool = True,
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Retrieval mode wrapper around shared explore_and_debate_hub."""
        return self.explore_and_debate_hub(
            query=query,
            chat_history=chat_history,
            allow_web_search=allow_web_search,
            project_id=project_id,
        )

    def evaluate_and_debate_ingestion(
        self,
        merged_concepts: List[Dict[str, Any]],
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> Dict[str, Any]:
        """Ingestion mode: Executes shared exploration & relevance debate first, then evaluates concept merging against hub knowledge."""
        exploration = self.explore_and_debate_hub(
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
            f"Persona Hub Knowledge Base & Observations:\n{exploration.get('perspective', '')}\n\n"
            f"Adjacent Subgraph Concepts:\n"
            f"{json.dumps([{'id': n.id, 'title': n.title, 'body': n.text_body[:200]} for n in subgraph_nodes], indent=2)}\n\n"
            f"Newly Extracted Candidate Concepts ({len(merged_concepts)} items):\n"
            f"{json.dumps(merged_concepts, indent=2)}"
        )

        messages = [
            {
                "role": "system",
                "content": load_prompt("persona_ingestion_evaluation").format(
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
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversing_node_ids": exploration.get("traversing_node_ids", []),
                "perspective": exploration.get("perspective", ""),
                "new_edges": data.get("new_edges", []),
                "merged_into_existing": data.get("merged_into_existing", []),
            }
        except Exception as e:
            print(f"[{self.department_name}] Ingestion evaluation error: {e}")
            return {
                "department_id": self.department_id,
                "department_name": self.department_name,
                "hub_node_id": self.hub_node.id,
                "traversing_node_ids": exploration.get("traversing_node_ids", []),
                "perspective": exploration.get("perspective", ""),
                "new_edges": [],
                "merged_into_existing": [],
            }
