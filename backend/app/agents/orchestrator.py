import json
import uuid
import time
from typing import List, Dict, Any, AsyncGenerator, Optional
from app.db import (
    db_engine,
    GraphNodeRecord,
    ConnectionEdgeRecord,
    PassageRecord,
    DocumentRecord,
    MacroDocumentRecord,
    StagingRecord,
)
from app.agents.department_persona import (
    DepartmentPersonaAgent,
    DEPARTMENT_PERSONA_COLORS,
)
from app.services.graph_analytics import graph_analytics
from app.services.llm_gateway import llm_gateway
from app.tools.search_tools import search_tools


class ExecutiveOrchestrator:
    """Executive Orchestrator agent coordinating Department Personas, graph retrieval debates, and delta ingestion."""

    def __init__(self):
        self.departments = [
            DepartmentPersonaAgent("Department of Latent World Models & Architectures"),
            DepartmentPersonaAgent("Department of Planning & Policy Control"),
            DepartmentPersonaAgent(
                "Department of Perceptual Representations & Sensors"
            ),
        ]

    async def execute_retrieval_flow(
        self, query: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """User Flow 2: Multi-Persona Parallel Debate Retrieval over Graph & Macro Documents."""
        yield {
            "event": "orchestrator_start",
            "message": f"Executive Orchestrator initiating multi-department retrieval for query: '{query}'",
            "timestamp": time.time(),
        }

        department_findings = []
        for dept in self.departments:
            # Emit SSE event for persona starting traversal with color code
            yield {
                "event": "persona_traversal_start",
                "department_name": dept.department_name,
                "color": dept.color,
                "message": f"Specialist {dept.department_name} traversing department seed concept hubs...",
                "timestamp": time.time(),
            }

            finding = dept.explore_and_debate_retrieval(query)
            department_findings.append(finding)

            # Emit SSE node highlight event for visual WebGL canvas
            yield {
                "event": "persona_traversal_active",
                "department_name": dept.department_name,
                "color": dept.color,
                "traversing_node_ids": finding["traversing_node_ids"],
                "perspective_snippet": finding["perspective"][:150],
                "timestamp": time.time(),
            }

        # Executive synthesis over department findings
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
        """User Flow 1: Staging -> Retrieval Debate -> Concept Evolution -> Passage Pointer Storage -> Macro Patch."""
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        passage_id = f"pass_{uuid.uuid4().hex[:8]}"

        # Step 1: Write raw document to disk and record metadata
        doc_rec = DocumentRecord(
            _id=doc_id,
            title=title,
            file_path=f"me-mex/data/documents/{doc_id}.txt",
            source_url=source_url,
        )
        db_engine.upsert_document(doc_rec)

        # Step 2: Create Out-Of-Graph Passage Record
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

        # Step 3: Multi-Persona Ingestion Debate for Concept Extraction & Superseding
        candidate_concepts = [
            {"title": f"{title} Dynamic Concept", "description": raw_text[:300]}
        ]

        delta_proposals = []
        for dept in self.departments:
            yield {
                "event": "persona_ingestion_debate",
                "department_name": dept.department_name,
                "color": dept.color,
                "message": f"{dept.department_name} evaluating graph evolution deltas and concept merging...",
                "timestamp": time.time(),
            }
            prop = dept.debate_ingestion_deltas(raw_text, candidate_concepts)
            delta_proposals.append(prop)

        # Step 4: Emit Human-In-The-Loop Prompt Event (if clarification needed)
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

        # Step 5: Evolve Graph Nodes (Add concept with passage pointers)
        concept_id = f"concept_{title.lower().replace(' ', '_')}"
        new_node = GraphNodeRecord(
            _id=concept_id,
            title=title,
            text_body=f"# {title}\n{raw_text[:500]}",
            passage_pointers=[passage_id],
            metadata={"status": "PRIMARY_ACTIVE"},
        )
        db_engine.upsert_node(new_node)

        # Connect edge from Root Concept to Action Planning
        edge_id = f"edge_{concept_id}_to_mpc"
        new_edge = ConnectionEdgeRecord(
            _id=edge_id,
            source_id=concept_id,
            target_id="concept_action_mpc",
            relation_type="BUILDS_UPON",
            text_body=f"Integration edge from {title} to MPC action planning.",
            weight=1.0,
            status="PRIMARY_ACTIVE",
        )
        db_engine.upsert_edge(new_edge)

        # Step 6: Trigger Delta Macro Document Update via Graph Analytics
        graph_analytics.update_macro_documents()

        yield {
            "event": "ingestion_complete",
            "concept_id": concept_id,
            "passage_pointers": [passage_id],
            "message": f"Successfully integrated node '{concept_id}' with passage pointers and patched Macro Documents.",
            "timestamp": time.time(),
        }


orchestrator = ExecutiveOrchestrator()
