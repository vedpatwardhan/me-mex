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
from typing import List, Dict, Any, AsyncGenerator, Generator, Optional, Union
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
    PassageRecord,
    DocumentRecord,
    IntentClassificationPayload,
    PassageConceptsPayload,
    ConsolidatedConceptsPayload,
    CollectiveLinkingPayload,
    ExploredDomainContext,
)
from app.agents.department_persona import (
    DepartmentPersonaAgent,
)
from app.services.logger import logger
from app.services.event_queue import event_queue
from app.services.graph_analytics import graph_analytics
from app.services.llm_gateway import llm_gateway
from app.services.llm_tracer import llm_tracer
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
        self.ingestion_engine = graph_ingestion_engine
        self.max_k_hubs = max_k_hubs

    @staticmethod
    def _extract_markdown_title(text: str) -> Optional[str]:
        """Extracts the document title from the first markdown heading (# , ## , ### ) in the text, ignoring comments and synthetic headers."""
        if not text:
            return None
        import re

        in_comment = False
        for line in text.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("<!--"):
                if not line_str.endswith("-->"):
                    in_comment = True
                continue
            if in_comment:
                if "-->" in line_str:
                    in_comment = False
                continue
            match = re.match(r"^#{1,6}\s+(.+)$", line_str)
            if match:
                candidate = match.group(1).strip()
                candidate = re.sub(r"[*_`]", "", candidate).strip()
                if candidate.lower() in (
                    "user context & notes",
                    "document content",
                    "user context",
                    "notes",
                ):
                    continue
                if len(candidate) >= 2:
                    return candidate
        return None

    def _chunk_text(
        self,
        text: str,
        chunk_size: Optional[int] = None,
        min_chunks: int = 1,
        max_chunks: int = 30,
        max_safe_chunk_size: int = 45000,
    ) -> List[str]:
        """Splits raw document text into cohesive passage chunks, scaling adaptively between min_chunks (1) and max_chunks (30) based on document length."""
        if not text:
            return []

        total_len = len(text)

        # 1. Compute dynamic target chunk count:
        # Tier 1 (<= 1.5k): 1 chunk (X post, brief note)
        # Tier 2 (1.5k - 4k): 2 chunks (short memo)
        # Tier 3 (4k - 8k): 3 chunks (medium article)
        # Tier 4 (8k - 14k): 4 chunks (long overview)
        # Tier 5 (14k - 25k): 5 chunks (short report)
        # Tier 6 (> 25k): 5 to 30 chunks (scaling up to 30 for >= 300k chars)
        if chunk_size is None:
            if total_len <= 1500:
                target_chunks = 1
            elif total_len <= 4000:
                target_chunks = 2
            elif total_len <= 8000:
                target_chunks = 3
            elif total_len <= 14000:
                target_chunks = 4
            elif total_len <= 25000:
                target_chunks = 5
            else:
                scaled_target = 5 + int((total_len - 25000) / 11000)
                target_chunks = max(min_chunks, min(max_chunks, scaled_target))

            calculated_size = (total_len + target_chunks - 1) // target_chunks
            chunk_size = min(max_safe_chunk_size, max(500, calculated_size))
        else:
            target_chunks = min_chunks

        # If document is short enough to fit entirely in 1 chunk and target is 1, return directly
        if target_chunks == 1 and total_len <= max_safe_chunk_size:
            return [text.strip()]

        # 2. Split into semantic paragraph units, breaking oversized paragraphs at sentence boundaries
        raw_paragraphs = text.split("\n\n")
        atomic_units: List[str] = []
        for p in raw_paragraphs:
            p_str = p.strip()
            if not p_str:
                continue
            if len(p_str) <= chunk_size:
                atomic_units.append(p_str)
            else:
                # Break large paragraph by sentences or newlines
                import re

                sentences = re.split(r"(?<=[.!?])\s+", p_str)
                curr_sentence_buf = ""
                for s in sentences:
                    if len(curr_sentence_buf) + len(s) + 1 <= chunk_size:
                        curr_sentence_buf += (" " if curr_sentence_buf else "") + s
                    else:
                        if curr_sentence_buf:
                            atomic_units.append(curr_sentence_buf)
                        curr_sentence_buf = s
                if curr_sentence_buf:
                    atomic_units.append(curr_sentence_buf)

        if not atomic_units:
            atomic_units = [text[:chunk_size]]

        # 3. Assemble atomic units into chunks up to target chunk_size
        chunks: List[str] = []
        curr = ""
        for unit in atomic_units:
            if len(curr) + len(unit) + 2 <= chunk_size:
                curr += ("\n\n" if curr else "") + unit
            else:
                if curr:
                    chunks.append(curr.strip())
                curr = unit
        if curr.strip():
            chunks.append(curr.strip())

        # 4. Target bound enforcement: subdivide if fewer chunks than target and text is substantial
        effective_min = max(min_chunks, target_chunks)
        while len(chunks) < effective_min and total_len > 1500:
            max_idx = max(range(len(chunks)), key=lambda i: len(chunks[i]))
            largest_chunk = chunks[max_idx]
            if len(largest_chunk) < 600:
                break  # cannot split any further without losing coherence

            # Split largest chunk roughly in half at paragraph or sentence boundary
            midpoint = len(largest_chunk) // 2
            split_pos = largest_chunk.rfind("\n\n", 0, midpoint + 200)
            if split_pos == -1 or split_pos < midpoint - 300:
                split_pos = largest_chunk.rfind(". ", 0, midpoint + 200)
                if split_pos != -1:
                    split_pos += 1  # include period

            if (
                split_pos == -1
                or split_pos <= 100
                or split_pos >= len(largest_chunk) - 100
            ):
                split_pos = midpoint

            part1 = largest_chunk[:split_pos].strip()
            part2 = largest_chunk[split_pos:].strip()
            if part1 and part2:
                chunks[max_idx] = part1
                chunks.insert(max_idx + 1, part2)
            else:
                break

        # 5. Upper bound enforcement: strictly merge shortest adjacent chunks until len(chunks) <= effective_max
        effective_max = min(max_chunks, max(target_chunks, min_chunks))
        while len(chunks) > effective_max:
            min_idx = 0
            min_combined_len = float("inf")
            for i in range(len(chunks) - 1):
                comb = len(chunks[i]) + len(chunks[i + 1])
                if comb < min_combined_len:
                    min_combined_len = comb
                    min_idx = i
            chunks[min_idx] = chunks[min_idx] + "\n\n" + chunks[min_idx + 1]
            chunks.pop(min_idx + 1)

        return chunks if chunks else [text[:chunk_size]]

    def _extract_concepts_from_passage(
        self,
        passage_text: str,
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
    ) -> PassageConceptsPayload:
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
        return self.llm.generate_structured_completion(
            messages,
            response_model=PassageConceptsPayload,
            temperature=0.2,
            max_tokens=2048,
            max_retries=2,
            enable_reasoning=False,
            caller="ExecutiveOrchestrator.extract_concepts_from_passage",
        )

    def consolidate_extracted_concepts(
        self,
        raw_extracted_concepts: List[Dict[str, Any]],
        doc_title: str,
        query: str,
        chat_history: List[Dict[str, str]],
    ) -> ConsolidatedConceptsPayload:
        """Consolidates raw passage concepts into document-specific canonical concepts in a single lean pass."""
        if not raw_extracted_concepts:
            return ConsolidatedConceptsPayload(
                doc_description=f"Empty knowledge document for '{doc_title}'.",
                doc_type="paper",
                concepts=[],
            )

        system_prompt = load_prompt("consolidate_concepts", doc_title=doc_title)
        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history[-4:])

        # Clean/project raw concept payloads to eliminate prompt bloat while preserving all semantic information
        lean_concepts = [
            {
                "title": c.get("title", ""),
                "description": c.get("description", ""),
                "passage_ids": c.get("passage_ids", []),
            }
            for c in raw_extracted_concepts
        ]

        payload_content = (
            f"User Query Context: {query}\n\n"
            f"Raw Passage Concept Extractions ({len(lean_concepts)} items):\n"
            f"{json.dumps(lean_concepts, indent=2)}"
        )
        messages.append({"role": "user", "content": payload_content})

        return self.llm.generate_structured_completion(
            messages,
            response_model=ConsolidatedConceptsPayload,
            temperature=0.2,
            max_tokens=4096,
            max_retries=2,
            enable_reasoning=False,
            caller="ExecutiveOrchestrator.consolidate_extracted_concepts",
        )

    def classify_intent(
        self, query: str, chat_history: List[Dict[str, str]]
    ) -> IntentClassificationPayload:
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

        payload = self.llm.generate_structured_completion(
            messages,
            response_model=IntentClassificationPayload,
            temperature=0.0,
            max_tokens=1024,
            max_retries=2,
            enable_reasoning=False,
            caller="ExecutiveOrchestrator.classify_intent",
        )

        if payload.intent == "INGESTION" and not payload.doc_type:
            raise ValueError(
                "Classified INGESTION intent but 'doc_type' is missing from LLM output."
            )

        return payload

    @staticmethod
    def _sanitize_chat_history(
        chat_history: Optional[List[Dict[str, str]]], max_len: int = 1024
    ) -> List[Dict[str, str]]:
        """Sanitizes incoming chat history turns to prevent oversized assistant messages from bloating prompts."""
        if not chat_history:
            return []
        sanitized = []
        for item in chat_history:
            content = item.get("content") or item.get("text", "")
            if len(content) > max_len:
                content = content[:max_len] + "..."
            sanitized.append({**item, "content": content})
        return sanitized

    async def process_user_message(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Central conversational entry point routing user input dynamically across the 3 execution paths."""
        chat_history = self._sanitize_chat_history(chat_history)
        llm_tracer.start_session(session_prefix="turn")

        async def _run_pipeline() -> AsyncGenerator[Dict[str, Any], None]:
            try:
                t0_intent = time.time()
                intent_payload = self.classify_intent(query, chat_history)
                intent_duration = round(time.time() - t0_intent, 2)
                intent = intent_payload.intent

                yield {
                    "event": "intent_classified",
                    "intent": intent,
                    "doc_type": intent_payload.doc_type,
                    "source_url": intent_payload.source_url,
                    "duration_seconds": intent_duration,
                    "message": f"Executive Orchestrator evaluated user input intent: '{intent}'",
                    "timestamp": time.time(),
                }

                if intent == "CONVERSATION":
                    async for event in self.execute_conversation_flow(
                        query, chat_history, project_id=project_id
                    ):
                        yield event
                elif intent == "INGESTION":
                    last_doc_title = None
                    async for event in self.execute_ingestion_flow(
                        query=query,
                        chat_history=chat_history,
                        target_info=intent_payload,
                        project_id=project_id,
                    ):
                        if event.get("event") == "ingestion_completed":
                            last_doc_title = event.get("title")
                        yield event

                    # Single conversational summary upon successful ingestion
                    summary_query = (
                        f"I just ingested document '{last_doc_title}'. Summarize key additions and integrated graph concepts."
                        if last_doc_title
                        else f"Summarize key additions from the recently ingested document for: {query}"
                    )
                    async for event in self.execute_conversation_flow(
                        summary_query, chat_history, project_id=project_id
                    ):
                        yield event
                else:
                    async for event in self.execute_retrieval_flow(
                        query=query,
                        chat_history=chat_history,
                        project_id=project_id,
                    ):
                        yield event
            except Exception as e:
                logger.error_box(
                    "Pipeline Error", f"Error during query '{query[:50]}': {e}"
                )
                yield {
                    "event": "error",
                    "error": str(e),
                    "message": f"Orchestrator encountered an error: {str(e)}",
                    "timestamp": time.time(),
                }
                fallback_prompt = (
                    f"An error occurred while handling the request ('{query}'): {str(e)}. "
                    "Briefly explain the issue to the user and suggest next steps."
                )
                try:
                    async for event in self.execute_conversation_flow(
                        fallback_prompt, chat_history, project_id=project_id
                    ):
                        yield event
                except Exception as fallback_err:
                    yield {
                        "event": "chat_complete",
                        "final_answer": f"I encountered an error while processing your request: {str(e)}",
                        "timestamp": time.time(),
                    }

        async for item in _run_pipeline():
            if isinstance(item, dict) and "event" in item:
                self.event_queue.push(project_id, item)
            yield item

    async def execute_conversation_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 1: CONVERSATION (Single-Step Direct Response straightaway)."""
        logger.phase_header(
            "💬 PATH 1: DIRECT CONVERSATIONAL FLOW",
            f"Project: {project_id} • Prompt: '{query[:80]}...'"
            if len(query) > 80
            else f"Project: {project_id} • Prompt: '{query}'",
            style="magenta",
        )

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
        async for token in self.llm.stream_chat_completion(
            messages, max_tokens=512, caller="ExecutiveOrchestrator.conversation"
        ):
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
                messages,
                max_tokens=512,
                caller="ExecutiveOrchestrator.conversation_fallback",
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
        logger.phase_header(
            "🔍 PATH 2: RETRIEVAL & SUB-GRAPH TRAVERSAL",
            f"Project: {project_id} • Query: '{query}'",
            style="green",
        )

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
        top_hub_nodes = [dept.hub_node for dept in active_departments]
        department_communities = self.analytics.partition_department_communities(
            project_id=project_id, hubs=top_hub_nodes
        )

        for dept in active_departments:
            yield {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona for '{dept.hub_node.title}' traversing adjacent concept edges...",
                "timestamp": time.time(),
            }

        async def _traverse_dept(dept):
            partition_ids = set(department_communities.get(dept.hub_node.id, []))
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
            yield {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversed_node_ids": finding["traversed_node_ids"],
                "timestamp": time.time(),
            }

        yield {
            "event": "retrieval_summary",
            "message": f"Graph Retrieval completed across {len(active_departments)} concept departments for query: '{query}'",
            "timestamp": time.time(),
        }

        # Final Step: Culminate in conversation response stream
        async for event in self.execute_conversation_flow(
            query, chat_history, project_id=project_id
        ):
            yield event

    async def execute_ingestion_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        target_info: IntentClassificationPayload,
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 3: INGESTION (Step 1: Fetch & Intra-Doc Graph -> Step 2: Hub Traversal, Relevance Eval, Linking & Reorganization -> Final Conversation)."""
        source_url = target_info.source_url
        raw_payload = target_info.raw_text

        logger.phase_header(
            "📥 PATH 3: DOCUMENT INGESTION PIPELINE",
            f"Project: {project_id} • Source: {source_url or 'Raw Text Payload'}",
            style="cyan",
        )

        # Step 1: Document Acquisition & Content Assembly
        # Ingestion requires a source_url (HTTP/HTTPS URL or file:// filesystem path).
        # raw_payload is contextual commentary and NEVER a substitute for the file contents!
        if not source_url:
            raise ValueError(
                "No document source URL or file path was provided for ingestion. "
                "Please provide a valid URL or local file path (e.g. file:///path/to/doc.pdf)."
            )

        doc_res = self.tools.fetch_document(source_url)
        fetch_status = doc_res.get("status", "SUCCESS")
        doc_type = doc_res.get("doc_type", target_info.doc_type or "document")
        page_count = doc_res.get("page_count")
        fetched_content = ""
        debug_file_path = ""
        fetch_error = None
        title = None

        if fetch_status == "SUCCESS" and doc_res.get("content"):
            fetched_content = doc_res.get("content", "")
            debug_file_path = doc_res.get("debug_file_path", "")
            # Title is 100% owned by the document itself (extracted strictly once)
            title = (
                self._extract_markdown_title(fetched_content)
                or f"Ingested Document {uuid.uuid4().hex[:6]}"
            )
        else:
            fetch_error = doc_res.get(
                "error", "Document could not be retrieved from source."
            )

        yield {
            "event": "document_fetched",
            "source_url": source_url,
            "title": title or "Unretrievable Document",
            "char_count": len(fetched_content),
            "debug_file_path": debug_file_path,
            "status": "SUCCESS" if not fetch_error else "ERROR",
            "error": fetch_error,
            "doc_type": doc_type,
            "page_count": page_count,
            "timestamp": time.time(),
        }

        # Step 2: SINGLE UNIFIED ERROR HANDLING
        if not fetched_content:
            raise RuntimeError(
                f"Document could not be retrieved from '{source_url}': {fetch_error}"
            )

        # Assemble full content: document content is primary, user notes attach as context
        full_content = (
            f"### User Context & Notes\n{raw_payload.strip()}\n\n"
            f"### Document Content\n{fetched_content.strip()}"
            if raw_payload
            else fetched_content
        )

        yield {
            "event": "orchestrator_tool_call",
            "tool_name": "ingest_document_tool",
            "args": {"title": title, "source_url": source_url},
            "message": f"Executive Orchestrator invoking document ingestion pipeline for '{title}'...",
            "timestamp": time.time(),
        }

        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        doc_rec = DocumentRecord(
            _id=doc_id,
            title=title,
            file_path=debug_file_path,
            source_url=source_url,
        )
        self.db.upsert_document(doc_rec)

        # Store Out-of-Graph Passage Records with dynamic adaptive chunking (scaling 1-30 passages based on document length)
        passage_chunks = self._chunk_text(full_content)
        passage_ids = []
        for idx, chunk_str in enumerate(passage_chunks):
            p_id = f"pass_{uuid.uuid4().hex[:8]}"
            p_rec = PassageRecord(
                _id=p_id, doc_id=doc_id, chunk_index=idx, text_content=chunk_str
            )
            self.db.upsert_passage(p_rec)
            passage_ids.append(p_id)

        yield {
            "event": "passages_chunked",
            "doc_id": doc_id,
            "doc_title": title,
            "chunk_count": len(passage_chunks),
            "timestamp": time.time(),
        }

        # Extract Raw Passage Concepts across chunks with bounded concurrency & Consolidate into Intra-Document Concepts
        raw_extracted_concepts: List[Dict[str, Any]] = []
        extraction_sem = asyncio.Semaphore(2)

        async def _extract_chunk(p_id: str, chunk_str: str, chunk_idx: int):
            async with extraction_sem:
                t0_chunk = time.time()
                extraction = await asyncio.to_thread(
                    self._extract_concepts_from_passage,
                    chunk_str,
                    title,
                    query,
                    chat_history,
                )
                chunk_duration = round(time.time() - t0_chunk, 2)
                c_count = len(extraction.concepts)
                c_titles = [c.title for c in extraction.concepts if c.title]
                evt_prog = {
                    "event": "passage_extraction_progress",
                    "doc_id": doc_id,
                    "chunk_index": chunk_idx + 1,
                    "total_chunks": len(passage_chunks),
                    "concepts_extracted": c_count,
                    "concept_titles": c_titles,
                    "duration_seconds": chunk_duration,
                    "timestamp": time.time(),
                }
                return p_id, extraction, evt_prog

        tasks = [
            asyncio.create_task(_extract_chunk(p_id, chunk_str, idx))
            for idx, (p_id, chunk_str) in enumerate(zip(passage_ids, passage_chunks))
        ]
        for fut in asyncio.as_completed(tasks):
            p_id, extraction, evt_prog = await fut
            yield evt_prog  # Stream progress event immediately in real-time!
            for c in extraction.concepts:
                raw_extracted_concepts.append(
                    {
                        "idx": c.idx,
                        "title": c.title,
                        "description": c.description or "",
                        "passage_ids": [p_id],
                    }
                )

        yield {
            "event": "passages_extracted",
            "doc_id": doc_id,
            "doc_title": title,
            "raw_concept_count": len(raw_extracted_concepts),
            "total_raw_concepts": len(raw_extracted_concepts),
            "timestamp": time.time(),
        }

        yield {
            "event": "consolidation_start",
            "doc_id": doc_id,
            "doc_title": title,
            "raw_concept_count": len(raw_extracted_concepts),
            "timestamp": time.time(),
        }

        t0_consol = time.time()
        consolidated_result = await asyncio.to_thread(
            self.consolidate_extracted_concepts,
            raw_extracted_concepts,
            title,
            query,
            chat_history,
        )
        consol_duration = round(time.time() - t0_consol, 2)

        consolidated_concepts = consolidated_result.concepts
        canonical_titles = [c.title for c in consolidated_concepts if c.title]

        yield {
            "event": "consolidation_complete",
            "doc_id": doc_id,
            "doc_title": title,
            "canonical_concepts_count": len(consolidated_concepts),
            "canonical_concepts": canonical_titles,
            "duration_seconds": consol_duration,
            "timestamp": time.time(),
        }

        proj_list = ["global"]
        if project_id and project_id != "global":
            proj_list.append(project_id)

        # Determine specific Document Root subtype (strictly required from intent classification)
        doc_type = target_info.doc_type
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
            description=consolidated_result.doc_description
            or f"Document summary for {title}.",
            passage_ids=passage_ids,
            project_ids=proj_list,
            metadata={
                "immutable": True,
                "source_url": source_url,
                "doc_type": doc_type,
            },
        )
        self.db.upsert_node(root_node)

        yield {
            "event": "root_node_created",
            "root_node_id": root_node_id,
            "node_type": doc_type,
            "title": title,
            "source_url": source_url,
            "timestamp": time.time(),
        }

        intra_doc_nodes = []
        for c in consolidated_concepts:
            c_id = f"concept_{uuid.uuid4().hex[:8]}"
            intra_node = GraphNode(
                _id=c_id,
                node_type="CONCEPT",
                title=c.title or "Extracted Concept",
                description=c.description or "",
                passage_ids=c.passage_ids or passage_ids[:1],
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

        yield {
            "event": "intra_concepts_created",
            "root_node_id": root_node_id,
            "count": len(intra_doc_nodes),
            "edges_count": len(intra_doc_nodes),
            "timestamp": time.time(),
        }

        # Step 2: Sub-Graph Traversal, Candidate Hub Assembly & Relevance Routing
        top_hubs = self.analytics.get_top_concept_hubs(
            project_id=project_id, max_k=self.max_k_hubs
        )
        yield {
            "event": "hubs_calculated",
            "hubs": [
                {"id": h.id, "title": h.title, "score": round(h.centrality_score, 4)}
                for h in top_hubs
            ],
            "count": len(top_hubs),
            "timestamp": time.time(),
        }

        # Phase 1: Pre-Check Persona Relevance Filtering (delegated to DepartmentPersonaAgent)
        selected_hub_ids = DepartmentPersonaAgent.filter_relevant_hubs(
            doc_title=title,
            intra_doc_nodes=intra_doc_nodes,
            candidate_hubs=[h.node for h in top_hubs],
            project_id=project_id,
        )

        # Filter active departments to ONLY the selected hubs
        selected_hub_set = set(selected_hub_ids)
        active_departments = [
            DepartmentPersonaAgent(h.node, h.centrality_score)
            for h in top_hubs
            if h.id in selected_hub_set
        ]

        evt_route_done = {
            "event": "persona_routing_completed",
            "active_hub_ids": [d.hub_node.id for d in active_departments],
            "active_hub_titles": [d.hub_node.title for d in active_departments],
            "bypassed_hub_titles": [
                h.title
                for h in top_hubs
                if h.id not in {d.hub_node.id for d in active_departments}
            ],
            "message": (
                f"Persona routing completed: activated {len(active_departments)} domain"
                f" hub(s) ({', '.join(d.hub_node.title for d in active_departments)})."
            ),
            "timestamp": time.time(),
        }
        yield evt_route_done
        print(f"[ExecutiveOrchestrator] {evt_route_done['message']}")

        # Partition network into mutually exclusive sub-graph communities anchored to detected active hubs
        top_hub_nodes = [dept.hub_node for dept in active_departments]
        department_communities = self.analytics.partition_department_communities(
            project_id=project_id, hubs=top_hub_nodes, max_depth=5
        )
        yield {
            "event": "partitions_calculated",
            "partitions": {
                dept.department_name: list(
                    department_communities.get(dept.hub_node.id, [])
                )
                for dept in active_departments
            },
            "timestamp": time.time(),
        }

        # Phase 2: Parallel Partitioned Sub-Graph Traversal for active personas
        collective_explored_trees: Dict[str, ExploredDomainContext] = {}

        for dept in active_departments:
            yield {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona for '{dept.hub_node.title}' exploring sub-graph partition during ingestion...",
                "timestamp": time.time(),
            }

            partition_ids = set(department_communities.get(dept.hub_node.id, []))
            traversal_finding = await asyncio.to_thread(
                dept.explore_concept_hub,
                query=query,
                chat_history=chat_history,
                project_id=project_id,
                max_depth=5,
                partition_node_ids=partition_ids if partition_ids else None,
            )

            for touch_evt in traversal_finding.get("emitted_events", []):
                yield touch_evt

            yield {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversed_node_ids": traversal_finding["traversed_node_ids"],
                "timestamp": time.time(),
            }

            # Store explored nodes per department for collective linking and post-reorganization
            dept_nodes_dict = {
                n.id: n for n in traversal_finding.get("explored_nodes", [])
            }
            dept_nodes_dict[dept.hub_node.id] = dept.hub_node
            collective_explored_trees[dept.hub_node.id] = ExploredDomainContext(
                department_id=dept.department_id,
                department_name=dept.department_name,
                hub_node=dept.hub_node,
                explored_nodes=list(dept_nodes_dict.values()),
            )

        # Phase 3: Collective Multi-Hub Ingestion Linking (Radial Invariant & Surjective Coverage)
        intra_concepts_payload = [n.to_prompt_dict() for n in intra_doc_nodes]
        available_domains_payload = [
            {
                "domain_hub_id": d_info.hub_node.id,
                "domain_name": d_info.department_name,
                "central_hub_node": d_info.hub_node.to_prompt_dict(),
                "intermediate_explored_concepts": [
                    n.to_prompt_dict()
                    for n in d_info.explored_nodes
                    if n.id != d_info.hub_node.id
                ],
            }
            for d_info in collective_explored_trees.values()
        ]

        system_collective = load_prompt("collective_ingestion_linking")
        user_collective = f"""Document Title: '{title}'
User Query: "{query}"

Newly Extracted Intra-Document Concepts ({len(intra_concepts_payload)} items, IMMUTABLE):
{json.dumps(intra_concepts_payload, indent=2)}

Available Active Persona Domains and Explored Sub-Graph Nodes:
{json.dumps(available_domains_payload, indent=2)}"""
        collective_commands = []
        try:
            payload_collective = self.llm.generate_structured_completion(
                [
                    {"role": "system", "content": system_collective},
                    {"role": "user", "content": user_collective},
                ],
                response_model=CollectiveLinkingPayload,
                temperature=0.2,
                max_tokens=4096,
                max_retries=2,
                enable_reasoning=False,
                caller="ExecutiveOrchestrator.collective_linking",
            )
            collective_commands = [c.model_dump() for c in payload_collective.commands]
        except Exception as e:
            print(f"[ExecutiveOrchestrator] Collective ingestion linking error: {e}")
            collective_commands = []

        # Execute collective linking commands into MongoDB with Radial Single-Attachment Enforcement
        # Map: (concept_id, domain_hub_id) -> chosen command (to enforce at most 1 connection per domain)
        domain_connections_tracker: dict[tuple[str, str], dict[str, Any]] = {}
        non_edge_commands: list[dict[str, Any]] = []

        # Pre-populate domain lookup map: node_id -> domain_hub_id
        node_to_domain_map: dict[str, str] = {}
        for h_id, d_info in collective_explored_trees.items():
            for n in d_info.explored_nodes:
                node_to_domain_map[n.id] = h_id

        for cmd in collective_commands:
            action = cmd.get("action")
            if action == "CREATE_EDGE":
                edge = cmd.get("edge", {})
                src = edge.get("source_id")
                tgt = edge.get("target_id")
                domain = edge.get("domain_hub_id") or node_to_domain_map.get(tgt)
                if src and tgt and domain:
                    pair_key = (src, domain)
                    # If already connected to this domain, prioritize deeper intermediate node over root hub
                    if pair_key not in domain_connections_tracker:
                        domain_connections_tracker[pair_key] = cmd
                    else:
                        existing_cmd = domain_connections_tracker[pair_key]
                        existing_tgt = existing_cmd.get("edge", {}).get("target_id")
                        if existing_tgt == domain and tgt != domain:
                            # Replace hub link with more specific intermediate node link
                            domain_connections_tracker[pair_key] = cmd
                else:
                    non_edge_commands.append(cmd)
            else:
                non_edge_commands.append(cmd)

        filtered_commands = (
            list(domain_connections_tracker.values()) + non_edge_commands
        )

        # Defensive Guard: Verify Surjective Coverage (Every concept must connect to at least one node)
        connected_concepts = {
            cmd.get("edge", {}).get("source_id")
            for cmd in filtered_commands
            if cmd.get("edge", {}).get("source_id")
        }

        # Fallback target: strictly prioritize primordial Genesis ('Everything') hub
        genesis_hub = self.db.get_genesis_node(project_id)
        for intra in intra_doc_nodes:
            if intra.id not in connected_concepts:
                filtered_commands.append(
                    {
                        "action": "CREATE_EDGE",
                        "department_name": genesis_hub.title,
                        "persona_id": genesis_hub.id,
                        "edge": {
                            "source_id": intra.id,
                            "target_id": genesis_hub.id,
                            "relation_type": "RELEVANT_TO",
                            "description": "Fallback foundational connection ensuring complete graph connectivity.",
                        },
                    }
                )

        for cmd in filtered_commands:
            # Map persona details if missing
            tgt = cmd.get("edge", {}).get("target_id")
            dept_id = node_to_domain_map.get(tgt)
            if dept_id and dept_id in collective_explored_trees:
                cmd["department_name"] = collective_explored_trees[
                    dept_id
                ].department_name
                cmd["persona_id"] = collective_explored_trees[dept_id].department_id
            evt = self.ingestion_engine.execute_single_command(cmd, title, proj_list)
            if evt:
                yield evt

        # Phase 4: Consolidated Post-Linking Macro-Reorganization
        # Runs ONCE after all edges are established into MongoDB
        for dept in active_departments:
            dept_context = collective_explored_trees.get(dept.hub_node.id)
            dept_explored = (
                dept_context.explored_nodes if dept_context else [dept.hub_node]
            )
            reorg_res = await asyncio.to_thread(
                dept.reorganize_concept_hub,
                explored_nodes=dept_explored,
                project_id=project_id,
                degree_threshold=5,
            )

            for reorg_evt in reorg_res.get("emitted_events", []):
                yield reorg_evt

            for cmd in reorg_res.get("commands", []):
                cmd["department_name"] = dept.department_name
                cmd["persona_id"] = dept.department_id
                evt = self.ingestion_engine.execute_single_command(
                    cmd, title, proj_list
                )
                if evt:
                    yield evt

        yield {
            "event": "ingestion_completed",
            "doc_id": doc_id,
            "title": title,
            "concepts_count": len(consolidated_concepts),
            "message": f"Document '{title}' successfully ingested and merged into knowledge graph.",
            "timestamp": time.time(),
        }


orchestrator = ExecutiveOrchestrator()
