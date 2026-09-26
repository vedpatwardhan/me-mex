import json
import uuid
import time
from typing import List, Dict, Any, AsyncGenerator, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
    PassageRecord,
    DocumentRecord,
    MacroDocumentRecord,
    StagingRecord,
)
from app.agents.department_persona import (
    DepartmentPersonaAgent,
)
from app.services.graph_analytics import graph_analytics
from app.services.llm_gateway import llm_gateway
from app.tools.search_tools import search_tools


class ExecutiveOrchestrator:
    """Executive Orchestrator agent acting as central intent classifier and coordinator for conversation, retrieval, and ingestion."""

    def __init__(self):
        pass

    def classify_intent(
        self, query: str, chat_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Classifies user input into DIRECT_CONVERSATION, GRAPH_RETRIEVAL, or DOCUMENT_INGESTION."""
        prompt = f"""
        Analyze the following user input and classify its primary intent into exactly ONE category:

        Categories:
        - "DIRECT_CONVERSATION": Greetings, general questions, conversational follow-ups, formatting, math, or basic Q&A that does not require deep graph traversal or new document ingestion.
        - "GRAPH_RETRIEVAL": Domain research, cross-paper synthesis, concept exploration, or queries asking about concepts/departments in the system.
        - "DOCUMENT_INGESTION": Input containing URLs (e.g. arXiv, YouTube, blogs), raw document text, paper abstracts, or explicit instructions to ingest/store content.

        User Input: "{query}"

        Return JSON format: {{"intent": "DIRECT_CONVERSATION" | "GRAPH_RETRIEVAL" | "DOCUMENT_INGESTION"}}
        """
        messages = [
            {
                "role": "system",
                "content": "You are the Executive Orchestrator intent classifier.",
            },
            {"role": "user", "content": prompt},
        ]
        try:
            res = llm_gateway.generate_chat_completion(messages)
            data = json.loads(res)
            intent = data.get("intent", "DIRECT_CONVERSATION").upper()
            if intent in [
                "DIRECT_CONVERSATION",
                "GRAPH_RETRIEVAL",
                "DOCUMENT_INGESTION",
            ]:
                return intent
        except Exception:
            pass

        # Simple heuristic fallback if JSON parsing or LLM synthetic fallback occurs
        lower_q = query.lower()
        if (
            lower_q.startswith("http")
            or "arxiv.org" in lower_q
            or "ingest" in lower_q
            or "paper abstract" in lower_q
        ):
            return "DOCUMENT_INGESTION"
        elif any(
            k in lower_q
            for k in [
                "compare",
                "synthesize",
                "explain",
                "concept",
                "department",
                "graph",
                "paper",
                "models",
                "retrieval",
                "search",
                "latent",
            ]
        ):
            return "GRAPH_RETRIEVAL"
        return "DIRECT_CONVERSATION"

    async def process_user_message(
        self, query: str, chat_history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Central conversational entry point routing user input dynamically."""
        intent = self.classify_intent(query, chat_history)

        yield {
            "event": "intent_classified",
            "intent": intent,
            "message": f"Executive Orchestrator evaluated user input intent: '{intent}'",
            "timestamp": time.time(),
        }

        if intent == "DIRECT_CONVERSATION":
            async for event in self.execute_direct_conversation_flow(
                query, chat_history
            ):
                yield event
        elif intent == "DOCUMENT_INGESTION":
            title = f"Ingested Document {uuid.uuid4().hex[:6]}"
            async for event in self.execute_ingestion_flow(title, query):
                yield event
        else:
            async for event in self.execute_retrieval_flow(query):
                yield event

    async def execute_direct_conversation_flow(
        self, query: str, chat_history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Direct conversational response without graph traversal overhead."""
        yield {
            "event": "conversation_start",
            "message": "Executive Orchestrator responding directly via conversational mode...",
            "timestamp": time.time(),
        }

        messages = [
            {
                "role": "system",
                "content": "You are Executive Orchestrator, an intelligent research assistant for Graph-Memex. Answer directly, concisely, and helpfully.",
            }
        ]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        direct_response = llm_gateway.generate_chat_completion(messages)

        yield {
            "event": "chat_complete",
            "final_answer": direct_response,
            "timestamp": time.time(),
        }

    async def execute_retrieval_flow(
        self, query: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Multi-Persona Parallel Retrieval over dynamically discovered Concept Hubs."""
        yield {
            "event": "persona_traversal_start",
            "message": f"Executive Orchestrator identifying dynamic concept hubs for query: '{query}'",
            "timestamp": time.time(),
        }

        # Dynamically discover top concept hubs via rustworkx centrality
        top_hubs = graph_analytics.get_top_concept_hubs(top_k=4)
        active_departments = [
            DepartmentPersonaAgent(hub_node, score) for hub_node, score in top_hubs
        ]

        if not active_departments:
            yield {
                "event": "no_personas_active",
                "message": "No active concept hubs found in database yet. Falling back to direct conversation.",
                "timestamp": time.time(),
            }
            async for event in self.execute_direct_conversation_flow(query):
                yield event
            return

        department_findings = []
        for dept in active_departments:
            yield {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona for '{dept.hub_node.title}' traversing adjacent concept edges...",
                "timestamp": time.time(),
            }

            finding = dept.explore_and_debate_retrieval(query)
            department_findings.append(finding)

            # Emit granular node_touched events as persona traverses adjacent nodes
            for node_id in finding["traversing_node_ids"]:
                node = db_engine.get_node(node_id)
                yield {
                    "event": "node_touched",
                    "persona_id": dept.department_id,
                    "persona_name": dept.department_name,
                    "node_id": node_id,
                    "node_title": node.title if node else node_id,
                    "message": f"Concept '{node.title if node else node_id}' touched by {dept.department_name}.",
                    "timestamp": time.time(),
                }

            if finding.get("web_search_used"):
                yield {
                    "event": "persona_web_search",
                    "department_id": dept.department_id,
                    "search_query": f"{dept.hub_node.title} {query}",
                    "message": f"Persona '{dept.department_name}' executed DuckDuckGo web search tool.",
                    "timestamp": time.time(),
                }

            yield {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversing_node_ids": finding["traversing_node_ids"],
                "perspective_snippet": finding["perspective"][:150],
                "timestamp": time.time(),
            }

        synthesis_prompt = f"Executive Orchestrator: Synthesize findings from concept hub personas into a final cohesive answer for query: '{query}'.\nDepartment Findings: {json.dumps(department_findings)}"
        messages = [
            {
                "role": "system",
                "content": "You are the Executive Orchestrator synthesising multi-persona graph intelligence.",
            },
            {"role": "user", "content": synthesis_prompt},
        ]
        final_answer = llm_gateway.generate_chat_completion(messages)

        yield {
            "event": "chat_complete",
            "final_answer": final_answer,
            "department_findings": department_findings,
            "timestamp": time.time(),
        }

    async def execute_ingestion_flow(
        self, title: str, raw_text: str, source_url: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Tool-based Ingestion: Save passage records, extract concept nodes, and form edges."""
        yield {
            "event": "orchestrator_tool_call",
            "tool_name": "ingest_document_tool",
            "args": {"title": title, "source_url": source_url},
            "message": f"Executive Orchestrator invoking document ingestion tool for '{title}'...",
            "timestamp": time.time(),
        }

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        passage_id = f"pass_{uuid.uuid4().hex[:8]}"

        doc_rec = DocumentRecord(
            _id=doc_id,
            title=title,
            file_path=f"me-mex/data/documents/{doc_id}.txt",
            source_url=source_url,
        )
        db_engine.upsert_document(doc_rec)

        pass_rec = PassageRecord(
            _id=passage_id, doc_id=doc_id, chunk_index=0, text_content=raw_text
        )
        db_engine.upsert_passage(pass_rec)

        concept_id = f"concept_{uuid.uuid4().hex[:6]}"
        new_node = GraphNode(
            _id=concept_id,
            node_type="concept",
            title=title,
            text_body=f"# {title}\n{raw_text[:500]}",
            passage_pointers=[passage_id],
            metadata={"status": "PRIMARY_ACTIVE"},
        )
        db_engine.upsert_node(new_node)

        # Connect new node to existing concept hubs if available
        top_hubs = graph_analytics.get_top_concept_hubs(top_k=1)
        if top_hubs:
            target_hub = top_hubs[0][0]
            edge_id = f"edge_{concept_id}_to_{target_hub.id}"
            new_edge = GraphEdge(
                _id=edge_id,
                source_id=concept_id,
                target_id=target_hub.id,
                is_directional=True,
                text_body=f"Ingested concept link from {title} to {target_hub.title}.",
                weight=1.0,
                status="PRIMARY_ACTIVE",
            )
            db_engine.upsert_edge(new_edge)

            yield {
                "event": "node_touched",
                "persona_id": "orchestrator",
                "persona_name": "Ingestion Engine",
                "node_id": concept_id,
                "node_title": title,
                "message": f"New node '{title}' created and linked to '{target_hub.title}'.",
                "timestamp": time.time(),
            }

        yield {
            "event": "tool_complete",
            "tool_name": "ingest_document_tool",
            "concept_id": concept_id,
            "passage_pointers": [passage_id],
            "message": f"Successfully integrated node '{concept_id}' with passage pointers.",
            "timestamp": time.time(),
        }


orchestrator = ExecutiveOrchestrator()
