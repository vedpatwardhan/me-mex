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
from app.services.ingest_summary import (
    build_ingestion_summary_user_message,
    query_asks_system_status,
)
from app.services.passage_packing import (
    default_passage_max_chars,
    max_passage_body_chars,
    pack_document_passages,
)
from app.services.retrieval_context import (
    build_closure_touch_events,
    collect_retrieval_subgraph,
    filter_retrieval_finding_by_relevance,
    format_retrieval_graph_context,
)


GRAPH_MUTATION_EVENTS = frozenset(
    {
        "root_node_created",
        "intra_concepts_created",
        "reorg_completed",
        "reorg_neighbor_rewired",
        "ingestion_completed",
    }
)


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
        *,
        summary_max_chars: Optional[int] = None,
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
            summary_max_chars=summary_max_chars,
        )

    def _extraction_context_blocks(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]],
        project_id: str,
    ) -> List[Dict[str, str]]:
        return self._ingest_context_blocks(
            query,
            chat_history,
            project_id,
            summary_max_chars=settings.INGEST_EXTRACTION_SUMMARY_MAX_CHARS,
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
        max_chunks: int = 40,
        max_safe_chunk_size: Optional[int] = None,
    ) -> List[str]:
        """Pack document text into the fewest passages that fit the vLLM input budget (see passage_packing)."""
        del min_chunks  # legacy param; packing minimizes call count instead of tier targets
        cap = chunk_size
        if cap is None:
            cap = settings.INGEST_PASSAGE_MAX_CHARS
        if cap is None:
            cap = max_safe_chunk_size or default_passage_max_chars()
        elif max_safe_chunk_size is not None:
            cap = min(cap, max_safe_chunk_size)
        return pack_document_passages(text, max_chunk_chars=cap, max_chunks=max_chunks)

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
        messages.extend(
            self._extraction_context_blocks(query, chat_history, project_id)
        )
        body_cap = max_passage_body_chars(doc_title)
        if len(passage_text) > body_cap:
            passage_text = passage_text[:body_cap]
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
            max_tokens=settings.LLM_COMPLETION_RESERVE_TOKENS,
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
        messages.extend(
            self._extraction_context_blocks(query, chat_history, project_id)
        )

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

        result = self.llm.generate_structured_completion(
            messages,
            response_model=ConsolidatedConceptsPayload,
            temperature=0.2,
            max_tokens=settings.CONSOLIDATION_MAX_TOKENS,
            max_retries=2,
            enable_reasoning=False,
            caller="ExecutiveOrchestrator.consolidate_extracted_concepts",
        )
        if len(result.doc_description) > 500:
            logger.warning(
                "Consolidation doc_description exceeds 500 chars; consider tightening prompt output."
            )
        for c in result.concepts:
            if len(c.description) > 400:
                logger.warning(
                    f"Consolidated concept '{c.title[:48]}' description exceeds 400 chars."
                )
        return result

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
                    ingestion_summary_ctx: Optional[Dict[str, Any]] = None
                    async for event in self.execute_ingestion_flow(
                        query=query,
                        chat_history=chat_history,
                        target_info=intent_payload,
                        project_id=project_id,
                    ):
                        if event.get("event") == "ingestion_completed":
                            ingestion_summary_ctx = {
                                "doc_title": event.get("title") or "",
                                "doc_description": event.get("doc_description") or "",
                                "canonical_concepts": event.get("canonical_concepts")
                                or [],
                            }
                        yield event

                    if ingestion_summary_ctx and ingestion_summary_ctx.get("doc_title"):
                        async for event in self.execute_ingestion_summary_flow(
                            doc_title=ingestion_summary_ctx["doc_title"],
                            doc_description=ingestion_summary_ctx["doc_description"],
                            canonical_concepts=ingestion_summary_ctx[
                                "canonical_concepts"
                            ],
                            project_id=project_id,
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
        graph_updated = False
        async for item in _run_pipeline():
            if isinstance(item, dict) and "event" in item:
                evt_type = item.get("event")
                if evt_type in GRAPH_MUTATION_EVENTS:
                    graph_updated = True
                if evt_type == "chat_complete":
                    last_reply = item.get("final_answer") or last_reply
                    item = {**item, "graph_updated": graph_updated}
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
        llm_caller: str = "ExecutiveOrchestrator.conversation",
        include_event_queue: Optional[bool] = None,
        max_tokens: Optional[int] = None,
        system_prompt_override: Optional[str] = None,
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

        attach_events = (
            include_event_queue
            if include_event_queue is not None
            else (
                settings.CONVERSATION_INCLUDE_EVENT_QUEUE
                or query_asks_system_status(query)
            )
        )
        events_summary = ""
        if attach_events:
            recent_events = self.event_queue.get_events(project_id=project_id, limit=15)
            if recent_events:
                formatted_events = [
                    f"- [{e.event_type}] {e.data.get('message') or e.data}"
                    for e in recent_events
                ]
                events_summary = (
                    "\n\nRecent System & Execution Events (Last 15 Queue):\n"
                    + "\n".join(formatted_events)
                )

        if system_prompt_override:
            base_prompt = system_prompt_override
        else:
            base_prompt = (
                load_prompt("retrieval_conversation")
                if grounded
                else load_prompt("conversation")
            )
        graph_block = ""
        if grounded:
            graph_block = (
                "\n\n--- Filtered graph context (answer ONLY from this subset) ---\n"
                f"{graph_context.strip()}\n"
                "--- End filtered context ---"
            )
        system_prompt = f"{base_prompt}{graph_block}{events_summary}"

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        completion_cap = (
            max_tokens
            if max_tokens is not None
            else settings.CHAT_COMPLETION_MAX_TOKENS
        )
        full_tokens = []
        async for token in self.llm.stream_chat_completion(
            messages,
            caller=llm_caller,
            max_tokens=completion_cap,
        ):
            full_tokens.append(token)
            yield {
                "event": "token_chunk",
                "delta": token,
                "timestamp": time.time(),
            }

        direct_response = "".join(full_tokens)
        if not direct_response:
            direct_response = self.llm.generate_chat_completion(
                messages,
                max_tokens=completion_cap,
                caller=f"{llm_caller}_fallback",
            )

        yield {
            "event": "chat_complete",
            "final_answer": direct_response,
            "timestamp": time.time(),
        }

    async def execute_ingestion_summary_flow(
        self,
        doc_title: str,
        doc_description: str,
        canonical_concepts: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Short user-facing message after ingestion (success + main concepts only)."""
        logger.phase_header(
            "📄 INGESTION USER SUMMARY",
            f"Project: {project_id} • Document: '{doc_title[:64]}'",
            style="cyan",
        )
        user_content = build_ingestion_summary_user_message(
            doc_title, doc_description, canonical_concepts
        )
        async for event in self.execute_conversation_flow(
            user_content,
            [],
            project_id=project_id,
            llm_caller="ExecutiveOrchestrator.ingestion_summary",
            include_event_queue=False,
            max_tokens=settings.INGESTION_SUMMARY_MAX_TOKENS,
            system_prompt_override=load_prompt("ingestion_complete_summary"),
        ):
            yield event

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
        trav_depth = (
            settings.RETRIEVAL_TRAVERSAL_MAX_DEPTH
            if settings.RETRIEVAL_TRAVERSAL_MAX_DEPTH is not None
            else settings.MAX_TRAVERSAL_DEPTH
        )
        hop_top_k = settings.RETRIEVAL_TRAVERSAL_TOP_K
        if hop_top_k is None:
            hop_top_k = settings.INGEST_TRAVERSAL_TOP_K

        stream_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def event_sink(evt: Dict[str, Any]) -> None:
            if evt.get("event") == "node_touched":
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("event", evt))

        def run_mutable_traversal() -> Dict[str, Any]:
            try:
                result = navigator.traverse_mutable_tree_from_genesis(
                    query=query,
                    chat_history=chat_history,
                    project_id=project_id,
                    max_depth=trav_depth,
                    traversal_top_k=hop_top_k,
                    ingest_context_messages=retrieval_ctx,
                    traversal_prompt="graph_tree_traversal_retrieval",
                    event_sink=event_sink,
                )
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("done", result))
                return result
            except Exception as exc:
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("error", exc))
                raise

        asyncio.create_task(asyncio.to_thread(run_mutable_traversal))
        base: Optional[Dict[str, Any]] = None
        while base is None:
            kind, payload = await stream_queue.get()
            if kind == "event":
                yield payload
            elif kind == "done":
                base = payload
            elif kind == "error":
                raise payload

        while not stream_queue.empty():
            kind, payload = stream_queue.get_nowait()
            if kind == "event":
                yield payload

        closure = await asyncio.to_thread(
            collect_retrieval_subgraph,
            base.get("explored_nodes", []),
            project_id,
        )
        for touch_evt in build_closure_touch_events(
            closure,
            base.get("traversed_node_ids", []),
            persona_id=navigator.department_id,
            persona_name=navigator.department_name,
        ):
            yield touch_evt
            await asyncio.sleep(0)

        finding = {**base, **closure}
        explored_count = len(finding.get("context_node_ids", []))
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

        finding = await asyncio.to_thread(
            filter_retrieval_finding_by_relevance,
            query,
            finding,
            chat_history=chat_history,
        )
        yield {
            "event": "retrieval_relevance_filtered",
            "message": (
                f"Narrowed retrieval context from {explored_count} explored nodes "
                f"to {len(finding.get('context_node_ids', []))} query-relevant nodes."
            ),
            "explored_context_count": explored_count,
            "filtered_context_count": len(finding.get("context_node_ids", [])),
            "context_node_ids": finding.get("context_node_ids", []),
            "answer_scope": finding.get("answer_scope", ""),
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
        passage_chunks = self._chunk_text(
            full_content,
            max_safe_chunk_size=max_passage_body_chars(title or ""),
        )
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
        stream_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def ingest_event_sink(evt: Dict[str, Any]) -> None:
            if (
                evt.get("event") == "node_touched"
                or evt.get("event") == "traversal_neighbors_truncated"
            ):
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("event", evt))

        def run_ingest_traversal() -> Dict[str, Any]:
            try:
                result = navigator.traverse_mutable_tree_from_genesis(
                    query=query,
                    chat_history=chat_history,
                    project_id=project_id,
                    max_depth=trav_depth,
                    traversal_top_k=settings.INGEST_TRAVERSAL_TOP_K,
                    ingest_context_messages=ingest_ctx,
                    event_sink=ingest_event_sink,
                )
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("done", result))
                return result
            except Exception as exc:
                loop.call_soon_threadsafe(stream_queue.put_nowait, ("error", exc))
                raise

        asyncio.create_task(asyncio.to_thread(run_ingest_traversal))
        traversal_finding: Optional[Dict[str, Any]] = None
        while traversal_finding is None:
            kind, payload = await stream_queue.get()
            if kind == "event":
                yield payload
            elif kind == "done":
                traversal_finding = payload
            elif kind == "error":
                raise payload

        for touch_evt in traversal_finding.get("emitted_events", []):
            if touch_evt.get("event") not in (
                "node_touched",
                "traversal_neighbors_truncated",
            ):
                yield touch_evt

        phase_timings["traversal"] = round(time.time() - t0_trav, 2)

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
            "doc_description": consolidated_result.doc_description or "",
            "canonical_concepts": [
                {"title": c.title, "description": c.description}
                for c in consolidated_concepts
                if c.title
            ],
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
