import json
from typing import List, Dict, Any, Optional
from app.db import (
    db_engine,
    MacroDocumentRecord,
    GraphNodeRecord,
    ConnectionEdgeRecord,
    PassageRecord,
)
from app.services.llm_gateway import llm_gateway

DEPARTMENT_PERSONA_COLORS = {
    "Department of Latent World Models & Architectures": "#38bdf8",  # Sky Blue
    "Department of Planning & Policy Control": "#fbbf24",  # Amber Yellow
    "Department of Perceptual Representations & Sensors": "#c084fc",  # Purple
    "Department of Foundation Robotics Systems": "#4ade80",  # Emerald Green
}


class DepartmentPersonaAgent:
    """Specialized Department Persona agent with distinct visual color coding for graph traversal."""

    def __init__(self, department_name: str):
        self.department_name = department_name
        self.color = DEPARTMENT_PERSONA_COLORS.get(department_name, "#38bdf8")

    def explore_and_debate_retrieval(self, query: str) -> Dict[str, Any]:
        """Phase 1 Retrieval Debate: Explore macro summary and seed concept nodes."""
        macros = db_engine.get_macros()
        dept_macro = next(
            (m for m in macros if m.department_name == self.department_name), None
        )

        traversed_node_ids = []
        relevant_concepts = []

        if dept_macro:
            for hub_id in dept_macro.hub_concept_ids:
                node = db_engine.get_node(hub_id)
                if node:
                    traversed_node_ids.append(node.id)
                    relevant_concepts.append(
                        {"id": node.id, "title": node.title, "summary": node.text_body}
                    )

        # Ask LLM via Gateway for department assessment
        messages = [
            {
                "role": "system",
                "content": f"You are the Lead Specialist of {self.department_name}. Analyze concept nodes and give an opinion on query: '{query}'.",
            },
            {
                "role": "user",
                "content": f"Department Macro Context: {dept_macro.summary_text if dept_macro else 'N/A'}\nRelevant concepts: {json.dumps(relevant_concepts)}",
            },
        ]
        llm_response = llm_gateway.generate_chat_completion(messages)

        return {
            "department_name": self.department_name,
            "color": self.color,
            "traversing_node_ids": traversed_node_ids,
            "perspective": llm_response,
            "relevant_concepts": relevant_concepts,
        }

    def debate_ingestion_deltas(
        self, staged_content: str, candidate_concepts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Phase 4 Ingestion Debate: Decide whether to MERGE, ADD NEW, or SUPERSEDE existing concept nodes."""
        existing_nodes = db_engine.get_nodes()
        nodes_summary = [
            {"id": n.id, "title": n.title, "passage_pointers": n.passage_pointers}
            for n in existing_nodes
        ]

        prompt = f"""
        You are the Lead Specialist of {self.department_name}.
        Analyze candidate concepts against existing department graph nodes:
        Existing Nodes: {json.dumps(nodes_summary)}
        New Staged Content: {staged_content[:1000]}
        Candidate Concepts: {json.dumps(candidate_concepts)}

        Determine:
        1. Should candidate concepts MERGE into existing nodes?
        2. Are old concept edges SUPERSEDED (decaying weight to 0.3)?
        3. Should new passage pointers be linked?
        """
        messages = [
            {
                "role": "system",
                "content": f"You are {self.department_name} specialist. Output structured JSON graph delta modifications.",
            },
            {"role": "user", "content": prompt},
        ]
        response = llm_gateway.generate_chat_completion(messages)
        return {
            "department_name": self.department_name,
            "color": self.color,
            "delta_proposal": response,
        }
