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
            "event": "orchestrator_intent_classified",
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
            "event": "conversation_complete",
            "final_answer": direct_response,
            "timestamp": time.time(),
        }

    async def execute_retrieval_flow(
        self, query: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Multi-Persona Parallel Debate Retrieval over dynamic DB Macro Documents."""
        yield {
            "event": "orchestrator_start",
            "message": f"Executive Orchestrator initiating multi-department retrieval for query: '{query}'",
            "timestamp": time.time(),
        }

        # Dynamically load active departments from macro documents stored in DB
        macros = db_engine.get_macros()
        active_departments = (
            [DepartmentPersonaAgent(m.department_name, m.department_id) for m in macros]
            if macros
            else []
        )

        if not active_departments:
            yield {
                "event": "no_personas_active",
                "message": "No department communities exist in database yet. Falling back to direct executive response.",
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
                "message": f"Specialist {dept.department_name} traversing department seed concept hubs...",
                "timestamp": time.time(),
            }

            finding = dept.explore_and_debate_retrieval(query)
            department_findings.append(finding)

            yield {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversing_node_ids": finding["traversing_node_ids"],
                "perspective_snippet": finding["perspective"][:150],
                "timestamp": time.time(),
            }

        synthesis_prompt = f"Executive Orchestrator: Synthesize findings from department personas into a final cohesive response for query: '{query}'.\nDepartment Findings: {json.dumps(department_findings)}"
        messages = [
            {
                "role": "system",
                "content": "You are the Executive Orchestrator synthesising multi-persona graph intelligence.",
            },
            {"role": "user", "content": synthesis_prompt},
        ]
        final_answer = llm_gateway.generate_chat_completion(messages)

        yield {
            "event": "retrieval_complete",
            "final_answer": final_answer,
            "department_findings": department_findings,
            "timestamp": time.time(),
        }

    async def execute_ingestion_flow(
        self, title: str, raw_text: str, source_url: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Staging -> Dynamic Ingestion Debate -> Concept Evolution -> Passage Storage -> Macro Patch."""
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

        yield {
            "event": "ingestion_staged",
            "doc_id": doc_id,
            "passage_id": passage_id,
            "message": f"Document '{title}' staged and stored in plain text passage records.",
            "timestamp": time.time(),
        }

        candidate_concepts = [
            {"title": f"{title} Dynamic Concept", "description": raw_text[:300]}
        ]

        delta_proposals = []
        macros = db_engine.get_macros()
        active_departments = [
            DepartmentPersonaAgent(m.department_name, m.department_id) for m in macros
        ]
        for dept in active_departments:
            yield {
                "event": "persona_ingestion_debate",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "message": f"{dept.department_name} evaluating graph evolution deltas and concept merging...",
                "timestamp": time.time(),
            }
            prop = dept.debate_ingestion_deltas(raw_text, candidate_concepts)
            delta_proposals.append(prop)

        yield {
            "event": "human_in_the_loop_prompt",
            "prompt_question": f"Should concept '{title}' supersede older pixel-space world model concepts or merge as a sub-concept?",
            "suggested_actions": [
                "SUPERSEDE_OLD",
                "MERGE_INTO_EXISTING",
                "CREATE_NEW_HUB",
            ],
            "timestamp": time.time(),
        }

        concept_id = f"concept_{title.lower().replace(' ', '_')}"
        new_node = GraphNode(
            _id=concept_id,
            title=title,
            text_body=f"# {title}\n{raw_text[:500]}",
            passage_pointers=[passage_id],
            metadata={"status": "PRIMARY_ACTIVE"},
        )
        db_engine.upsert_node(new_node)

        edge_id = f"edge_{concept_id}_to_mpc"
        new_edge = GraphEdge(
            _id=edge_id,
            source_id=concept_id,
            target_id="concept_action_mpc",
            is_directional=True,
            text_body=f"Integration edge from {title} to MPC action planning.",
            weight=1.0,
            status="PRIMARY_ACTIVE",
        )
        db_engine.upsert_edge(new_edge)

        graph_analytics.update_macro_documents()

        yield {
            "event": "ingestion_complete",
            "concept_id": concept_id,
            "passage_pointers": [passage_id],
            "message": f"Successfully integrated node '{concept_id}' with passage pointers and patched Macro Documents.",
            "timestamp": time.time(),
        }


orchestrator = ExecutiveOrchestrator()
