"""
Executive Orchestrator Agent: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 2:
- Acts as central conversational gateway and intent classifier.
- Classifies queries into 3 execution paths (`CONVERSATION`, `RETRIEVAL`, `INGESTION`).
- Path Lifecycle:
    - `CONVERSATION`: Direct execution -> Final conversation response.
    - `RETRIEVAL`: Genesis tree traversal + immutable evidence closure (Step 1) -> Grounded conversation response (Step 2).
    - `INGESTION`: Fetch URL/PDF & build intra-doc graph (Step 1) -> Genesis tree traversal, collective linking & passage-grounded concept splitting (Step 2) -> Final conversation response.
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
    TargetGeneralizationPayload,
)
from app.config import settings
from app.agents.graph_navigator import GraphNavigator
from app.services.graph_analytics import graph_analytics, MutableTreeIndex
from app.services.logger import logger
from app.services.event_queue import event_queue
from app.services.graph_analytics import graph_analytics
from app.services.llm_gateway import llm_gateway
from app.services.llm_tracer import llm_tracer
from app.services.prompt_mapper import PromptIdMapper
from app.tools.search_tools import search_tools
from app.prompts import load_prompt
from app.services.graph_ingestion_engine import graph_ingestion_engine
from app.services.ingest_payload import ingest_context_message_blocks, json_dumps_ingest
from app.services.conversation_summary import (
    get_rolling_summary,
    schedule_rolling_summary_refresh,
)
from app.services.retrieval_context import format_retrieval_graph_context


class ExecutiveOrchestrator:
    """Executive Orchestrator agent acting as central intent classifier and lifecycle coordinator."""

    def __init__(self):
        self.db = db_engine
        self.analytics = graph_analytics
        self.llm = llm_gateway
        self.tools = search_tools
        self.event_queue = event_queue
        self.ingestion_engine = graph_ingestion_engine

    def _ingest_context_blocks(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]],
        project_id: str,
    ) -> List[Dict[str, str]]:
        summary = (
            get_rolling_summary(project_id)
            if settings.INGEST_USE_ROLLING_SUMMARY
            else None
        )
        return ingest_context_message_blocks(
            query,
            rolling_summary=summary,
            chat_history=chat_history,
        )

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
        project_id: str = "global",
    ) -> PassageConceptsPayload:
        """Performs LLM pass across a passage chunk to extract atomic concept nodes and qualitative relation edges."""
        system_prompt = load_prompt("passage_concept_extraction", doc_title=doc_title)
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._ingest_context_blocks(query, chat_history, project_id))
        messages.append(
            {
                "role": "user",
                "content": f"Passage Chunk ({doc_title}):\n{passage_text}",
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
        passage_mapper: Optional[PromptIdMapper] = None,
        project_id: str = "global",
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
        messages.extend(self._ingest_context_blocks(query, chat_history, project_id))

        # Clean/project raw concept payloads with integer passage_indices
        lean_concepts = []
        for c in raw_extracted_concepts:
            p_ids = c.get("passage_ids", [])
            p_indices = []
            if passage_mapper:
                p_indices = [
                    passage_mapper.to_index(pid)
                    for pid in p_ids
                    if passage_mapper.to_index(pid) is not None
                ]
            else:
                p_indices = [1]
            lean_concepts.append(
                {
                    "title": c.get("title", ""),
                    "description": c.get("description", ""),
                    "passage_indices": p_indices,
                }
            )

        payload_content = (
            f"Raw Passage Concept Extractions ({len(lean_concepts)} items):\n"
            f"{json_dumps_ingest(lean_concepts)}"
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
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> IntentClassificationPayload:
        """Classifies user input into CONVERSATION, RETRIEVAL, or INGESTION path in a single pass."""
        system_prompt = load_prompt("classify_intent")

        messages = [{"role": "system", "content": system_prompt}]
        if settings.INGEST_USE_ROLLING_SUMMARY:
            summary = (get_rolling_summary(project_id) or "").strip()
            if summary:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Conversation context (rolling summary for this project):\n"
                            f"{summary[: settings.CHAT_SUMMARY_MAX_CHARS]}"
                        ),
                    }
                )
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
                intent_payload = self.classify_intent(
                    query, chat_history, project_id=project_id
                )
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

        last_reply = ""
        async for item in _run_pipeline():
            if isinstance(item, dict) and "event" in item:
                if item.get("event") == "chat_complete":
                    last_reply = item.get("final_answer") or last_reply
                self.event_queue.push(project_id, item)
            yield item
        await schedule_rolling_summary_refresh(
            project_id,
            chat_history or [],
            latest_user_query=query,
            latest_assistant_reply=last_reply,
        )

    async def execute_conversation_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
        graph_context: Optional[str] = None,
        max_tokens: Optional[int] = None,
        llm_caller: str = "ExecutiveOrchestrator.conversation",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 1: CONVERSATION (Single-Step Direct Response straightaway)."""
        grounded = bool(graph_context and graph_context.strip())
        logger.phase_header(
            "💬 PATH 1: DIRECT CONVERSATIONAL FLOW"
            if not grounded
            else "💬 PATH 2: GROUNDED RETRIEVAL RESPONSE",
            f"Project: {project_id} • Prompt: '{query[:80]}...'"
            if len(query) > 80
            else f"Project: {project_id} • Prompt: '{query}'",
            style="magenta" if not grounded else "green",
        )

        yield {
            "event": "conversation_start",
            "message": (
                "Executive Orchestrator synthesizing answer from retrieved graph context..."
                if grounded
                else "Executive Orchestrator responding directly via conversational mode..."
            ),
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
        graph_block = ""
        if grounded:
            graph_block = (
                "\n\n--- Retrieved Knowledge Graph Context (use as primary factual grounding) ---\n"
                f"{graph_context.strip()}\n"
                "--- End retrieved context ---"
            )
        system_prompt = f"{base_prompt}{graph_block}{events_summary}"

        messages = [{"role": "system", "content": system_prompt}]
        token_budget = (
            max_tokens
            if max_tokens is not None
            else (settings.RETRIEVAL_ANSWER_MAX_TOKENS if grounded else 512)
        )
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        # Stream tokens progressively
        full_tokens = []
        async for token in self.llm.stream_chat_completion(
            messages, max_tokens=token_budget, caller=llm_caller
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
                max_tokens=token_budget,
                caller=f"{llm_caller}_fallback",
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
        """Path 2: RETRIEVAL (Genesis tree traversal -> evidence closure -> grounded conversation)."""
        logger.phase_header(
            "🔍 PATH 2: RETRIEVAL & SUB-GRAPH TRAVERSAL",
            f"Project: {project_id} • Query: '{query}'",
            style="green",
        )

        navigator = GraphNavigator(project_id=project_id)
        yield {
            "event": "graph_traversal_start",
            "navigator_id": navigator.navigator_id,
            "genesis_id": navigator.genesis_node.id,
            "message": f"Graph Navigator traversing mutable tree from '{navigator.genesis_node.title}' for query: '{query}'",
            "timestamp": time.time(),
        }

        retrieval_ctx = self._ingest_context_blocks(query, chat_history, project_id)
        finding = await asyncio.to_thread(
            navigator.explore_for_retrieval,
            query=query,
            chat_history=chat_history,
            project_id=project_id,
            ingest_context_messages=retrieval_ctx,
        )
        for touch_evt in finding.get("emitted_events", []):
            yield touch_evt

        yield {
            "event": "graph_traversal_active",
            "navigator_id": navigator.navigator_id,
            "traversed_node_ids": finding.get("traversed_node_ids", []),
            "context_node_ids": finding.get("context_node_ids", []),
            "immutable_evidence_count": len(
                finding.get("immutable_evidence_nodes", [])
            ),
            "timestamp": time.time(),
        }

        graph_context = format_retrieval_graph_context(
            finding,
            genesis_description=navigator.genesis_node.description,
            max_chars=settings.RETRIEVAL_CONTEXT_MAX_CHARS,
        )

        yield {
            "event": "retrieval_summary",
            "message": (
                f"Graph retrieval completed from Genesis for query: '{query}' "
                f"({len(finding.get('context_node_ids', []))} context nodes)."
            ),
            "context_node_ids": finding.get("context_node_ids", []),
            "timestamp": time.time(),
        }

        async for event in self.execute_conversation_flow(
            query,
            chat_history,
            project_id=project_id,
            graph_context=graph_context,
            llm_caller="ExecutiveOrchestrator.retrieval_conversation",
        ):
            yield event

    async def execute_ingestion_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        target_info: IntentClassificationPayload,
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Path 3: INGESTION (Fetch & intra-doc graph -> tree traversal, linking, reorganization -> conversation)."""
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
        # and register them into a dedicated Passage Cache Map (passage_id <-> passage_index)
        passage_mapper = PromptIdMapper(prefix="passage")
        passage_chunks = self._chunk_text(full_content)
        passage_ids = []
        for idx, chunk_str in enumerate(passage_chunks):
            p_id = f"pass_{uuid.uuid4().hex[:8]}"
            p_rec = PassageRecord(
                _id=p_id, doc_id=doc_id, chunk_index=idx, text_content=chunk_str
            )
            self.db.upsert_passage(p_rec)
            passage_ids.append(p_id)
            passage_mapper.register(p_id)

        yield {
            "event": "passages_chunked",
            "doc_id": doc_id,
            "doc_title": title,
            "chunk_count": len(passage_chunks),
            "timestamp": time.time(),
        }

        # Extract Raw Passage Concepts across chunks with bounded concurrency & Consolidate into Intra-Document Concepts
        raw_extracted_concepts: List[Dict[str, Any]] = []
        extraction_sem = asyncio.Semaphore(settings.INGEST_EXTRACTION_CONCURRENCY)
        phase_timings: Dict[str, float] = {}
        ingest_t0 = time.time()

        async def _extract_chunk(p_id: str, chunk_str: str, chunk_idx: int):
            async with extraction_sem:
                t0_chunk = time.time()
                extraction = await asyncio.to_thread(
                    self._extract_concepts_from_passage,
                    chunk_str,
                    title,
                    query,
                    chat_history,
                    project_id,
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
            passage_mapper,
            project_id,
        )
        consol_duration = round(time.time() - t0_consol, 2)
        phase_timings["extraction_and_consolidation"] = round(
            time.time() - ingest_t0, 2
        )

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
            # Decode integer passage_indices back to real string passage_ids using the passage mapper
            resolved_pids = [
                passage_mapper.to_id(p_idx)
                for p_idx in c.passage_indices
                if passage_mapper.to_id(p_idx) is not None
            ]
            intra_node = GraphNode(
                _id=c_id,
                node_type="CONCEPT",
                title=c.title or "Extracted Concept",
                description=c.description or "",
                passage_ids=resolved_pids or passage_ids[:1],
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
                description="",
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

        # Step 2: Genesis tree traversal & linking
        navigator = GraphNavigator(project_id=project_id)
        yield {
            "event": "graph_traversal_start",
            "navigator_id": navigator.navigator_id,
            "genesis_id": navigator.genesis_node.id,
            "message": f"Graph Navigator exploring mutable tree for ingestion of '{title}'",
            "timestamp": time.time(),
        }

        ingest_ctx = self._ingest_context_blocks(query, chat_history, project_id)
        trav_depth = (
            settings.INGEST_TRAVERSAL_MAX_DEPTH
            if settings.INGEST_TRAVERSAL_MAX_DEPTH is not None
            else settings.MAX_TRAVERSAL_DEPTH
        )
        t0_trav = time.time()
        traversal_finding = await asyncio.to_thread(
            navigator.traverse_mutable_tree_from_genesis,
            query=query,
            chat_history=chat_history,
            project_id=project_id,
            max_depth=trav_depth,
            traversal_top_k=settings.INGEST_TRAVERSAL_TOP_K,
            ingest_context_messages=ingest_ctx,
        )
        phase_timings["traversal"] = round(time.time() - t0_trav, 2)
        for touch_evt in traversal_finding.get("emitted_events", []):
            yield touch_evt

        explored_nodes = list(
            {n.id: n for n in traversal_finding.get("explored_nodes", [])}.values()
        )

        yield {
            "event": "graph_traversal_active",
            "navigator_id": navigator.navigator_id,
            "traversed_node_ids": traversal_finding.get("traversed_node_ids", []),
            "timestamp": time.time(),
        }

        # Phase 3: Tree-grounded ingestion linking
        # Dedicated Concept Cache Map for intra concepts and explored target nodes
        linking_concept_mapper = PromptIdMapper(prefix="concept")

        intra_concepts_payload = []
        for n in intra_doc_nodes:
            c_idx = linking_concept_mapper.register(n.id)
            intra_concepts_payload.append(
                {"concept_index": c_idx, "title": n.title, "description": n.description}
            )

        # ToDo: try to get these anchor paths from the traverse_mutable_tree_from_genesis result
        explored_tree_payload = []
        link_tree = MutableTreeIndex(project_id=project_id)
        genesis_id = navigator.genesis_node.id
        mutable_anchor_paths = []
        for n in explored_nodes:
            n_idx = linking_concept_mapper.register(n.id)
            explored_tree_payload.append(
                {
                    "target_index": n_idx,
                    "title": n.title,
                    "description": n.description,
                    "is_genesis": n.id == genesis_id,
                }
            )
            path_ids = list(reversed(link_tree.path_to_genesis(n.id)))
            path_from_genesis = []
            for depth, pid in enumerate(path_ids):
                pnode = self.db.get_node(pid)
                if not pnode or pnode.is_root_node:
                    continue
                p_idx = linking_concept_mapper.register(pid)
                path_from_genesis.append(
                    {
                        "target_index": p_idx,
                        "title": pnode.title,
                        "depth_from_genesis": depth,
                        "is_genesis": pid == genesis_id,
                    }
                )
            mutable_anchor_paths.append(
                {
                    "frontier_target_index": n_idx,
                    "path_from_genesis": path_from_genesis,
                }
            )

        system_collective = load_prompt("collective_ingestion_linking")
        user_collective = f"""Document Title: '{title}'

Newly Extracted Intra-Document Concepts ({len(intra_concepts_payload)} items, IMMUTABLE):
{json_dumps_ingest(intra_concepts_payload)}

Explored Mutable Tree Nodes (Genesis-rooted traversal, {len(explored_tree_payload)} nodes):
{json_dumps_ingest(explored_tree_payload)}

Mutable anchor paths (Genesis → frontier; use for highest-suitable-anchor linking):
{json_dumps_ingest(mutable_anchor_paths)}"""
        collective_commands = []
        link_messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_collective},
        ]
        link_messages.extend(ingest_ctx)
        link_messages.append({"role": "user", "content": user_collective})
        t0_link = time.time()
        try:
            payload_collective = self.llm.generate_structured_completion(
                link_messages,
                response_model=CollectiveLinkingPayload,
                temperature=0.2,
                max_tokens=4096,
                max_retries=2,
                enable_reasoning=False,
                caller="ExecutiveOrchestrator.collective_linking",
            )
            # Decode model integer indices back to string database IDs
            for c in payload_collective.commands:
                src_id = linking_concept_mapper.to_id(c.edge.source_index)
                tgt_id = linking_concept_mapper.to_id(c.edge.target_index)
                if src_id and tgt_id:
                    collective_commands.append(
                        {
                            "action": c.action,
                            "edge": {
                                "source_id": src_id,
                                "target_id": tgt_id,
                                "description": c.edge.description or "",
                            },
                        }
                    )
        except Exception as e:
            print(f"[ExecutiveOrchestrator] Collective ingestion linking error: {e}")
            collective_commands = []

        filtered_commands = list(collective_commands)

        # Defensive Guard: Verify Surjective Coverage (Every concept must connect to at least one node)
        connected_concepts = {
            cmd.get("edge", {}).get("source_id")
            for cmd in filtered_commands
            if cmd.get("edge", {}).get("source_id")
        }

        genesis_node = navigator.genesis_node
        for intra in intra_doc_nodes:
            if intra.id not in connected_concepts:
                filtered_commands.append(
                    {
                        "action": "CREATE_EDGE",
                        "edge": {
                            "source_id": intra.id,
                            "target_id": genesis_node.id,
                            "description": "Fallback foundational connection ensuring complete graph connectivity.",
                        },
                    }
                )

        for cmd in filtered_commands:
            cmd.setdefault("navigator_id", navigator.navigator_id)
            cmd.setdefault("navigator_name", navigator.navigator_name)
            evt = self.ingestion_engine.execute_single_command(cmd, title, proj_list)
            if evt:
                yield evt

        graph_analytics.refresh_tree_metadata(project_id)

        # Phase 3.5: Targeted Generalization Pass on Affected Target Nodes
        # Gathers all mutable target nodes that received new connections during this ingestion pass
        # and generalizes their titles and descriptions to accommodate all connected concepts.
        affected_target_ids = {
            cmd.get("edge", {}).get("target_id")
            for cmd in filtered_commands
            if cmd.get("action") == "CREATE_EDGE"
            and cmd.get("edge", {}).get("target_id")
        }
        mutable_targets = [self.db.get_node(t_id) for t_id in affected_target_ids]
        mutable_targets = [
            n for n in mutable_targets if n is not None and not n.is_immutable
        ]

        phase_timings["linking"] = round(time.time() - t0_link, 2)

        if mutable_targets:
            t0_gen = time.time()
            async for gen_evt in self._generalize_affected_target_nodes(
                mutable_targets=mutable_targets,
                project_id=project_id,
                query=query,
                chat_history=chat_history,
            ):
                yield gen_evt
            phase_timings["generalization"] = round(time.time() - t0_gen, 2)

        # Phase 4: Reorganization on link-affected mutable targets (degree ≥ τ → LLM discover → split)
        t0_reorg = time.time()
        reorg_res = await asyncio.to_thread(
            navigator.reorganize_overclustered_nodes,
            mutable_targets,
            project_id=project_id,
            degree_threshold=settings.DEGREE_THRESHOLD,
            doc_title=title,
            proj_list=proj_list,
            plan_only=False,
            link_affected_ids=set(affected_target_ids),
        )
        for reorg_evt in reorg_res.get("emitted_events", []):
            yield reorg_evt
        graph_analytics.refresh_tree_metadata(project_id)
        phase_timings["reorganization"] = round(time.time() - t0_reorg, 2)
        phase_timings["total_ingestion"] = round(time.time() - ingest_t0, 2)

        yield {
            "event": "ingestion_phase_timings",
            "timings": phase_timings,
            "timestamp": time.time(),
        }

        yield {
            "event": "ingestion_completed",
            "doc_id": doc_id,
            "title": title,
            "concepts_count": len(consolidated_concepts),
            "message": f"Document '{title}' successfully ingested and merged into knowledge graph.",
            "timestamp": time.time(),
        }

        await schedule_rolling_summary_refresh(
            project_id,
            chat_history or [],
            latest_user_query=query,
        )

    async def _generalize_affected_target_nodes(
        self,
        mutable_targets: List[GraphNode],
        project_id: str = "global",
        query: str = "",
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Synthesizes updated titles and descriptions for mutable concept nodes that received new connections during ingestion."""
        if not mutable_targets:
            return

        all_edges = self.db.get_edges(project_id)
        # Build adjacency for targets
        adj_map: Dict[str, List[GraphEdge]] = defaultdict(list)
        for e in all_edges:
            adj_map[e.source_id].append(e)
            adj_map[e.target_id].append(e)

        gen_mapper = PromptIdMapper(prefix="target")
        targets_payload = []
        target_map: Dict[int, GraphNode] = {}

        for node in mutable_targets:
            n_idx = gen_mapper.register(node.id)
            target_map[n_idx] = node

            # Gather connected neighbors
            neighbors = []
            for edge in adj_map.get(node.id, []):
                nb_id = edge.target_id if edge.source_id == node.id else edge.source_id
                nb_node = self.db.get_node(nb_id)
                if nb_node:
                    neighbors.append(
                        {
                            "title": nb_node.title,
                            "description": nb_node.description,
                            "is_immutable": nb_node.is_immutable,
                        }
                    )

            targets_payload.append(
                {
                    "node_index": n_idx,
                    "current_title": node.title,
                    "current_description": node.description,
                    "is_genesis_node": node.title.lower() == "everything",
                    "connected_concepts_count": len(neighbors),
                    "connected_concepts": neighbors,
                }
            )

        system_gen = load_prompt("target_node_generalization")
        user_gen = f"""Target Nodes That Received New Ingestion Connections ({len(targets_payload)} nodes):
{json_dumps_ingest(targets_payload)}"""
        gen_messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_gen},
        ]
        gen_messages.extend(
            self._ingest_context_blocks(query, chat_history, project_id)
        )
        gen_messages.append({"role": "user", "content": user_gen})

        try:
            payload = await asyncio.to_thread(
                self.llm.generate_structured_completion,
                gen_messages,
                response_model=TargetGeneralizationPayload,
                temperature=0.2,
                max_tokens=2048,
                max_retries=2,
                enable_reasoning=False,
                caller="ExecutiveOrchestrator.generalize_affected_target_nodes",
            )

            for item in payload.generalizations:
                target_node = target_map.get(item.node_index)
                if not target_node:
                    continue

                old_title = target_node.title
                # Invariant: If primordial 'Everything' node, keep title unchanged
                if target_node.title.lower() != "everything" and item.updated_title:
                    target_node.title = item.updated_title.strip()
                if item.updated_description:
                    target_node.description = item.updated_description.strip()

                target_node.updated_at = time.time()
                self.db.upsert_node(target_node)

                evt = {
                    "event": "node_touched",
                    "persona_id": f"dept_{target_node.id}",
                    "persona_name": f"Persona Specialist: {target_node.title}",
                    "node_id": target_node.id,
                    "node_title": target_node.title,
                    "message": (
                        f"Generalized concept '{target_node.title}' to accommodate newly attached concepts."
                        if old_title == target_node.title
                        else f"Generalized concept '{old_title}' -> '{target_node.title}' to accommodate newly attached concepts."
                    ),
                    "timestamp": time.time(),
                }
                yield evt

        except Exception as e:
            print(f"[ExecutiveOrchestrator] Targeted generalization pass error: {e}")


orchestrator = ExecutiveOrchestrator()
