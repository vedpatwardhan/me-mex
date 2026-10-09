"""
Executive Orchestrator Agent: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 2:
- Acts as central conversational gateway and intent classifier.
- Classifies queries into 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`).
- Path Lifecycle:
    - `CONVERSATION`: Direct execution -> Final conversation response.
    - `RETRIEVAL`: Mutually exclusive sub-graph traversal (Step 1) -> Relevance evaluation (Step 2) -> Final conversation response.
    - `INGESTION`: Fetch URL/PDF & build intra-doc graph (Step 1) -> Partitioned sub-graph traversal, relevance eval, multi-hub linking & passage-grounded concept splitting (Step 2) -> Final conversation response.
- Creates Root Nodes (`ROOT`) and extracted Intra-Document Concepts (`node_type="CONCEPT"`) with `immutable: True`.
"""

import json
import uuid
import time
import asyncio
from collections import defaultdict
from typing import List, Dict, Any, AsyncGenerator, Generator, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
    PassageRecord,
    DocumentRecord,
)
from app.agents.department_persona import (
    DepartmentPersonaAgent,
)
from app.services.event_queue import event_queue
from app.services.graph_analytics import graph_analytics
from app.services.llm_gateway import llm_gateway
from app.tools.search_tools import search_tools
from app.prompts import load_prompt
from app.services.graph_ingestion_engine import graph_ingestion_engine


class ExecutiveOrchestrator:
    """Executive Orchestrator agent acting as central intent classifier and lifecycle coordinator."""

    def __init__(self, max_k_hubs: int = 5):
        self.db = db_engine
        self.analytics = graph_analytics
        self.llm = llm_gateway
        self.tools = search_tools
        self.event_queue = event_queue
        self.max_k_hubs = max_k_hubs
        self.ingestion_engine = graph_ingestion_engine

    def _chunk_text(self, text: str, chunk_size: int = 1500) -> List[str]:
        """Splits raw document text into fixed ~500 token (~1500 character) passage chunks."""
        if not text:
            return []
        paragraphs = text.split("\n\n")
        chunks = []
        curr = ""
        for p in paragraphs:
            if len(curr) + len(p) <= chunk_size:
                curr += ("\n\n" if curr else "") + p
            else:
                if curr:
                    chunks.append(curr.strip())
                curr = p
        if curr.strip():
            chunks.append(curr.strip())
        return chunks if chunks else [text[:chunk_size]]

    def _extract_concepts_from_passage(
        self,
        passage_text: str,
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Performs LLM pass across a passage chunk to extract atomic concept nodes and qualitative relation edges."""
        system_prompt = load_prompt("passage_concept_extraction", doc_title=doc_title)
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history[-4:])
        messages.append(
            {
                "role": "user",
                "content": f"User Query Context: {query}\n\nPassage Chunk ({doc_title}):\n{passage_text}",
            }
        )
        try:
            res = self.llm.generate_chat_completion(
                messages,
                temperature=0.2,
                max_tokens=512,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            return {
                "concepts": data.get("concepts", []),
                "relations": data.get("relations", []),
            }
        except Exception:
            return {
                "concepts": [
                    {"idx": 0, "title": doc_title, "description": passage_text}
                ],
                "relations": [],
            }

    def consolidate_extracted_concepts(
        self,
        raw_extracted_concepts: List[Dict[str, Any]],
        extracted_relations: List[Dict[str, Any]],
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Consolidates raw passage concepts into document-specific canonical concepts."""
        if not raw_extracted_concepts:
            return {"concepts": [], "relations": []}

        system_prompt = load_prompt("consolidate_concepts", doc_title=doc_title)
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history[-4:])

        payload_content = (
            f"User Query Context: {query}\n\n"
            f"Raw Passage Concept Extractions ({len(raw_extracted_concepts)} items):\n"
            f"{json.dumps(raw_extracted_concepts, indent=2)}\n\n"
            f"Raw Passage Relations ({len(extracted_relations)} items):\n"
            f"{json.dumps(extracted_relations, indent=2)}"
        )
        messages.append({"role": "user", "content": payload_content})

        try:
            res = self.llm.generate_chat_completion(
                messages,
                temperature=0.2,
                max_tokens=2048,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            return {
                "doc_description": data.get(
                    "doc_description",
                    f"Consolidated knowledge document for '{doc_title}'.",
                ),
                "doc_type": data.get("doc_type", "paper"),
                "concepts": data.get("concepts", []),
                "relations": data.get("relations", []),
            }
        except Exception as e:
            print(f"[ExecutiveOrchestrator] Concept consolidation LLM pass error: {e}")
            return {
                "doc_description": f"Consolidated knowledge document for '{doc_title}'.",
                "doc_type": "paper",
                "concepts": raw_extracted_concepts,
                "relations": extracted_relations,
            }

    def classify_intent(
        self, query: str, chat_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Classifies user input into CONVERSATION, RETRIEVAL, or INGESTION path in a single pass."""
        system_prompt = load_prompt("classify_intent")

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            for item in chat_history[-4:]:
                role = (
                    "assistant"
                    if item.get("role") in ("agent", "assistant")
                    else "user"
                )
                content = item.get("content") or item.get("text", "")
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})

        try:
            res = self.llm.generate_chat_completion(
                messages,
                temperature=0.0,
                max_tokens=256,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            raw_intent = data.get("intent", "CONVERSATION")

            if raw_intent == "INGESTION":
                doc_type = data.get("doc_type")
                if not doc_type:
                    raise ValueError(
                        "Classified INGESTION intent but 'doc_type' is missing from LLM output."
                    )
                return {
                    "intent": "INGESTION",
                    "doc_type": doc_type,
                    "source_url": data.get("source_url"),
                    "raw_text": data.get("raw_text"),
                }

            # CONVERSATION or RETRIEVAL
            return {
                "intent": raw_intent,
                "doc_type": None,
                "source_url": None,
                "raw_text": None,
            }
        except Exception as e:
            print(f"[ExecutiveOrchestrator] classify_intent error: {e}")
            return {
                "intent": "CONVERSATION",
                "doc_type": None,
                "source_url": None,
                "raw_text": None,
            }

    async def process_user_message(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Central conversational entry point routing user input dynamically across the 3 execution paths."""
        if chat_history is None:
            chat_history = []
        try:
            intent_result = self.classify_intent(query, chat_history)
            intent = intent_result["intent"]

            intent_evt = {
                "event": "intent_classified",
                "intent": intent,
                "message": f"Executive Orchestrator evaluated user input intent: '{intent}'",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, intent_evt)
            yield intent_evt

            if intent == "CONVERSATION":
                async for event in self.execute_conversation_flow(
                    query, chat_history, project_id=project_id
                ):
                    self.event_queue.push(project_id, event)
                    yield event
            elif intent == "INGESTION":
                async for event in self.execute_ingestion_flow(
                    query=query,
                    chat_history=chat_history,
                    target_info=intent_result,
                    project_id=project_id,
                ):
                    self.event_queue.push(project_id, event)
                    yield event
            else:
                async for event in self.execute_retrieval_flow(
                    query=query,
                    chat_history=chat_history,
                    project_id=project_id,
                ):
                    self.event_queue.push(project_id, event)
                    yield event
        except Exception as e:
            err_evt = {
                "event": "error",
                "error": str(e),
                "message": f"Orchestrator encountered an error: {str(e)}",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, err_evt)
            yield err_evt

    async def execute_conversation_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 1: CONVERSATION (Single-Step Direct Response straightaway)."""
        yield {
            "event": "conversation_start",
            "message": "Executive Orchestrator responding directly via conversational mode...",
            "timestamp": time.time(),
        }

        recent_events = self.event_queue.get_events(project_id=project_id, limit=15)
        events_summary = ""
        if recent_events:
            formatted_events = [
                f"- [{e.event_type}] {e.data.get('message') or e.data}"
                for e in recent_events
            ]
            events_summary = (
                "\n\nRecent System & Execution Events (Last 15 Queue):\n"
                + "\n".join(formatted_events)
            )

        base_prompt = load_prompt("conversation")
        system_prompt = f"{base_prompt}{events_summary}"

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        # Stream tokens progressively
        full_tokens = []
        async for token in self.llm.stream_chat_completion(messages, max_tokens=1024):
            full_tokens.append(token)
            yield {
                "event": "token_chunk",
                "delta": token,
                "timestamp": time.time(),
            }

        direct_response = "".join(full_tokens)
        if not direct_response:
            # Fallback to direct synchronous generation if streaming returns empty
            direct_response = self.llm.generate_chat_completion(
                messages, max_tokens=1024
            )

        yield {
            "event": "chat_complete",
            "final_answer": direct_response,
            "timestamp": time.time(),
        }

    async def execute_retrieval_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 2: RETRIEVAL (Step 1: Partitioned Hub Traversal -> Step 2: Relevance Evaluation -> Final Conversation)."""
        yield {
            "event": "persona_traversal_start",
            "message": f"Executive Orchestrator identifying dynamic concept hubs in project '{project_id}' for query: '{query}'",
            "timestamp": time.time(),
        }

        # Discover top concept hubs via rustworkx unweighted centrality
        top_hubs = self.analytics.get_top_concept_hubs(
            project_id=project_id, max_k=self.max_k_hubs
        )
        active_departments = [
            DepartmentPersonaAgent(hub_node, score) for hub_node, score in top_hubs
        ]

        if not active_departments:
            yield {
                "event": "no_personas_active",
                "message": "No active concept hubs found in database yet. Falling back to direct conversation.",
                "timestamp": time.time(),
            }
            async for event in self.execute_conversation_flow(
                query, chat_history, project_id=project_id
            ):
                yield event
            return

        # Pre-Step 1 & 2: Mutually Exclusive Sub-Graph Traversal & Relevance Evaluation
        department_communities = self.analytics.partition_department_communities(
            project_id
        )

        for dept in active_departments:
            start_evt = {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona for '{dept.hub_node.title}' traversing adjacent concept edges...",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, start_evt)
            yield start_evt

        async def _traverse_dept(dept):
            partition_ids = set(department_communities.get(dept.department_name, []))
            finding = await asyncio.to_thread(
                dept.explore_concept_hub,
                query=query,
                chat_history=chat_history,
                project_id=project_id,
                max_depth=3,
                partition_node_ids=partition_ids if partition_ids else None,
            )
            return dept, finding

        traversal_results = await asyncio.gather(
            *[_traverse_dept(dept) for dept in active_departments]
        )

        department_findings = []
        for dept, finding in traversal_results:
            department_findings.append(finding)
            evt_active = {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversed_node_ids": finding["traversed_node_ids"],
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, evt_active)
            yield evt_active

        retrieval_summary_evt = {
            "event": "retrieval_summary",
            "message": f"Graph Retrieval completed across {len(active_departments)} concept departments for query: '{query}'",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, retrieval_summary_evt)

        # Final Step: Culminate in conversation response stream
        async for event in self.execute_conversation_flow(
            query, chat_history, project_id=project_id
        ):
            yield event

    async def execute_ingestion_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        target_info: Dict[str, Any],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 3: INGESTION (Step 1: Fetch & Intra-Doc Graph -> Step 2: Hub Traversal, Relevance Eval, Linking & Reorganization -> Final Conversation)."""
        source_url = target_info.get("source_url")
        raw_payload = target_info.get("raw_text")

        # Step 1: Document Fetching & Content Assembly
        fetched_content = ""
        title = None

        if source_url:
            doc_res = self.tools.fetch_document(source_url)
            fetched_content = doc_res.get("content", "")
            debug_file_path = doc_res.get("debug_file_path", "")
            fetch_status = doc_res.get("status", "SUCCESS")
            error_msg = doc_res.get(
                "error", "Document could not be retrieved from URL."
            )

            if fetched_content:
                for line in fetched_content.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

            evt_fetched = {
                "event": "document_fetched",
                "source_url": source_url,
                "title": title or "Fetched Document",
                "char_count": len(fetched_content),
                "debug_file_path": debug_file_path,
                "status": fetch_status,
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, evt_fetched)
            yield evt_fetched

            # If download failed and there is no user raw text payload to ingest, abort ingestion immediately and transition to conversation
            if (fetch_status == "ERROR" or not fetched_content) and not raw_payload:
                print(
                    f"[ExecutiveOrchestrator] Document download failed for {source_url}. Aborting ingestion flow and initiating conversation response."
                )
                fail_query = (
                    f"I attempted to ingest the document at '{source_url}', but downloading and extracting content failed ({error_msg}). "
                    f"Inform the user clearly that the document could not be retrieved from this URL and suggest checking the URL or providing the text directly."
                )
                async for event in self.execute_conversation_flow(
                    fail_query, chat_history, project_id=project_id
                ):
                    yield event
                return

        # Combine both fetched content and user commentary if both exist
        if fetched_content and raw_payload:
            full_content = (
                f"### User Context & Notes\n{raw_payload.strip()}\n\n"
                f"### Document Content\n{fetched_content.strip()}"
            )
        elif fetched_content:
            full_content = fetched_content
        else:
            full_content = raw_payload or ""

        if not full_content.strip():
            print(
                "[ExecutiveOrchestrator] Ingestion aborted: No content available to ingest."
            )
            async for event in self.execute_conversation_flow(
                "No content or document was provided for ingestion. Inform the user to provide a valid document URL or text.",
                chat_history,
                project_id=project_id,
            ):
                yield event
            return

        if not title:
            first_line = (
                full_content.strip().splitlines()[0]
                if (full_content and full_content.strip())
                else ""
            )
            if first_line and len(first_line) < 80:
                title = first_line.lstrip("#").strip()
            else:
                title = f"Ingested Document {uuid.uuid4().hex[:6]}"

        tool_evt = {
            "event": "orchestrator_tool_call",
            "tool_name": "ingest_document_tool",
            "args": {"title": title, "source_url": source_url},
            "message": f"Executive Orchestrator invoking document ingestion pipeline for '{title}'...",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, tool_evt)
        yield tool_evt

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc_rec = DocumentRecord(
            _id=doc_id,
            title=title,
            file_path=f"me-mex/data/documents/{doc_id}.txt",
            source_url=source_url,
        )
        self.db.upsert_document(doc_rec)

        # Store Out-of-Graph Passage Records
        passage_chunks = self._chunk_text(full_content, chunk_size=1500)
        passage_ids = []
        for idx, chunk_str in enumerate(passage_chunks):
            p_id = f"pass_{uuid.uuid4().hex[:8]}"
            p_rec = PassageRecord(
                _id=p_id, doc_id=doc_id, chunk_index=idx, text_content=chunk_str
            )
            self.db.upsert_passage(p_rec)
            passage_ids.append(p_id)

        evt_chunks = {
            "event": "passages_chunked",
            "doc_id": doc_id,
            "doc_title": title,
            "chunk_count": len(passage_chunks),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_chunks)
        yield evt_chunks

        # Extract Raw Passage Concepts concurrently across all chunks & Consolidate into Intra-Document Concepts
        raw_extracted_concepts: List[Dict[str, Any]] = []
        extracted_relations: List[Dict[str, Any]] = []

        async def _extract_chunk(p_id: str, chunk_str: str, chunk_idx: int):
            extraction = await asyncio.to_thread(
                self._extract_concepts_from_passage,
                chunk_str,
                title,
                query,
                chat_history,
            )
            c_count = len(extraction.get("concepts", []))
            evt_prog = {
                "event": "passage_extraction_progress",
                "doc_id": doc_id,
                "chunk_index": chunk_idx + 1,
                "total_chunks": len(passage_chunks),
                "concepts_extracted": c_count,
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, evt_prog)
            return p_id, extraction, evt_prog

        extractions = await asyncio.gather(
            *[
                _extract_chunk(p_id, chunk_str, idx)
                for idx, (p_id, chunk_str) in enumerate(
                    zip(passage_ids, passage_chunks)
                )
            ]
        )
        for p_id, extraction, evt_prog in extractions:
            yield evt_prog
            for c in extraction.get("concepts", []):
                raw_extracted_concepts.append(
                    {
                        "idx": c["idx"],
                        "title": c["title"],
                        "description": c.get("description", ""),
                        "passage_ids": [p_id],
                    }
                )
            extracted_relations.extend(extraction.get("relations", []))

        evt_extracted = {
            "event": "passages_extracted",
            "doc_id": doc_id,
            "total_raw_concepts": len(raw_extracted_concepts),
            "total_raw_relations": len(extracted_relations),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_extracted)
        yield evt_extracted

        evt_consol_start = {
            "event": "consolidation_start",
            "doc_id": doc_id,
            "doc_title": title,
            "raw_concept_count": len(raw_extracted_concepts),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_consol_start)
        yield evt_consol_start

        consolidated_result = self.consolidate_extracted_concepts(
            raw_extracted_concepts, extracted_relations, title, query, chat_history
        )
        consolidated_concepts = consolidated_result.get("concepts", [])

        evt_consol_complete = {
            "event": "consolidation_complete",
            "doc_id": doc_id,
            "doc_title": title,
            "canonical_concepts_count": len(consolidated_concepts),
            "canonical_relations_count": len(consolidated_result.get("relations", [])),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_consol_complete)
        yield evt_consol_complete

        proj_list = ["global"]
        if project_id and project_id != "global":
            proj_list.append(project_id)

        # Determine specific Document Root subtype (strictly required from intent classification)
        doc_type = target_info.get("doc_type")
        if not doc_type:
            raise ValueError(
                "Ingestion execution aborted: 'doc_type' is strictly required for ingestion and cannot be missing or None."
            )

        # Create Root Node & Immutable Intra-Document Concept Nodes in MongoDB
        root_node_id = f"root_{doc_id}"
        root_node = GraphNode(
            _id=root_node_id,
            node_type=doc_type,
            title=title,
            description=consolidated_result.get(
                "doc_description", f"Document summary for {title}."
            ),
            passage_ids=passage_ids,
            project_ids=proj_list,
            metadata={
                "immutable": True,
                "source_url": source_url,
                "doc_type": doc_type,
            },
        )
        self.db.upsert_node(root_node)

        evt_root_created = {
            "event": "root_node_created",
            "root_node_id": root_node_id,
            "node_type": doc_type,
            "title": title,
            "source_url": source_url,
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_root_created)
        yield evt_root_created

        intra_doc_nodes = []
        for c in consolidated_concepts:
            c_id = f"concept_{uuid.uuid4().hex[:8]}"
            intra_node = GraphNode(
                _id=c_id,
                node_type="CONCEPT",
                title=c.get("title", "Extracted Concept"),
                description=c.get("description", ""),
                passage_ids=c.get("passage_ids", passage_ids[:1]),
                project_ids=proj_list,
                metadata={"immutable": True, "root_node_id": root_node_id},  # IMMUTABLE
            )
            self.db.upsert_node(intra_node)
            intra_doc_nodes.append(intra_node)

            # Link Root Node to Intra-Document Concept
            rel_edge = GraphEdge(
                _id=f"edge_{uuid.uuid4().hex[:8]}",
                source_id=root_node_id,
                target_id=c_id,
                description="RELEVANT_TO",
                project_ids=proj_list,
            )
            self.db.upsert_edge(rel_edge)

        evt_intra_created = {
            "event": "intra_concepts_created",
            "root_node_id": root_node_id,
            "count": len(intra_doc_nodes),
            "edges_count": len(intra_doc_nodes),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_intra_created)
        yield evt_intra_created

        # Step 2: Sub-Graph Traversal, Relevance Eval, Multi-Hub Linking & Concept Reorganization
        top_hubs = self.analytics.get_top_concept_hubs(
            project_id=project_id, max_k=self.max_k_hubs
        )
        evt_hubs = {
            "event": "hubs_calculated",
            "hubs": [
                {"id": h[0].id, "title": h[0].title, "score": round(h[1], 4)}
                for h in top_hubs
            ],
            "count": len(top_hubs),
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_hubs)
        yield evt_hubs

        active_departments = [
            DepartmentPersonaAgent(hub_node, score) for hub_node, score in top_hubs
        ]

        # Partition network into mutually exclusive sub-graph communities
        department_communities = self.analytics.partition_department_communities(
            project_id
        )
        evt_parts = {
            "event": "partitions_calculated",
            "partitions": {
                dept_name: list(node_ids)
                for dept_name, node_ids in department_communities.items()
            },
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, evt_parts)
        yield evt_parts

        for dept in active_departments:
            yield {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona for '{dept.hub_node.title}' exploring sub-graph partition during ingestion...",
                "timestamp": time.time(),
            }

            # 1. Partitioned Sub-Graph Traversal
            partition_ids = set(department_communities.get(dept.department_name, []))
            traversal_finding = dept.explore_concept_hub(
                query=query,
                chat_history=chat_history,
                project_id=project_id,
                max_depth=3,
                partition_node_ids=partition_ids if partition_ids else None,
            )

            # Telemetry: Active persona traversal nodes
            evt_active = {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversed_node_ids": traversal_finding["traversed_node_ids"],
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, evt_active)
            yield evt_active

            # 2. Ingestion Linking (Immediate execution into MongoDB)
            ingest_res = dept.persona_ingestion(
                intra_doc_nodes,
                title,
                query,
                traversal_finding["explored_nodes"],
                chat_history=chat_history,
                project_id=project_id,
            )
            for cmd in ingest_res.get("commands", []):
                cmd["department_name"] = dept.department_name
                evt = self.ingestion_engine.execute_single_command(
                    cmd, title, proj_list
                )
                if evt:
                    self.event_queue.push(project_id, evt)
                    yield evt

            # 3. Non-Destructive Concept Hub Reorganization (Operating on real-time graph state)
            reorg_cmds = dept.reorganize_concept_hub(
                explored_nodes=traversal_finding["explored_nodes"],
                project_id=project_id,
            )
            for cmd in reorg_cmds:
                cmd["department_name"] = dept.department_name
                evt = self.ingestion_engine.execute_single_command(
                    cmd, title, proj_list
                )
                if evt:
                    self.event_queue.push(project_id, evt)
                    yield evt

        summary_evt = {
            "event": "ingestion_completed",
            "doc_id": doc_id,
            "title": title,
            "concepts_count": len(consolidated_concepts),
            "message": f"Document '{title}' successfully ingested and merged into knowledge graph.",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, summary_evt)
        yield summary_evt

        # Final Step: Culminate in conversation response stream
        ingest_query = f"I just ingested document '{title}'. Summarize key additions and integrated graph concepts."
        async for event in self.execute_conversation_flow(
            ingest_query, chat_history, project_id=project_id
        ):
            yield event


orchestrator = ExecutiveOrchestrator()
