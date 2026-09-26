import json
from typing import List, Dict, Any, Optional
from app.db import db_engine
from app.models import (
    MacroDocumentRecord,
    GraphNode,
    GraphEdge,
    PassageRecord,
)
from app.services.llm_gateway import llm_gateway


class DepartmentPersonaAgent:
    """Specialized Persona Agent instantiated dynamically per concept hub."""

    def __init__(self, hub_node: GraphNode, score: float = 1.0):
        self.hub_node = hub_node
        self.score = score
        self.department_id = f"dept_{hub_node.id}"
        self.department_name = f"Persona Specialist: {hub_node.title}"

    def explore_and_debate_retrieval(
        self, query: str, allow_web_search: bool = True, project_id: str = "global"
    ) -> Dict[str, Any]:
        """Explore hub node body, adjacent sub-graph edges, and optionally execute DuckDuckGo web search tool."""
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

        prompt = f"""
        You are the Specialist Agent for Concept Hub '{self.hub_node.title}'.
        Your Hub Concept Node Details:
        - Title: {self.hub_node.title}
        - Description: {self.hub_node.text_body}

        Adjacent Subgraph Concepts:
        {json.dumps([{"id": n.id, "title": n.title, "body": n.text_body[:200]} for n in subgraph_nodes])}
        {web_search_results}

        Task / User Query: "{query}"

        Analyze the task from your concept hub perspective. Provide concise, expert observations.
        """
        messages = [
            {
                "role": "system",
                "content": f"You are the persona specialist for '{self.hub_node.title}'.",
            },
            {"role": "user", "content": prompt},
        ]
        llm_response = llm_gateway.generate_chat_completion(messages)

        return {
            "department_id": self.department_id,
            "department_name": self.department_name,
            "hub_node_id": self.hub_node.id,
            "traversing_node_ids": traversed_node_ids,
            "perspective": llm_response,
            "web_search_used": bool(web_search_results),
        }
