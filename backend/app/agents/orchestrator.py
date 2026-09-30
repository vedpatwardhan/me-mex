import json
import uuid
import time
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


class ExecutiveOrchestrator:
    """Executive Orchestrator agent acting as central intent classifier and coordinator for conversation, retrieval, and ingestion."""

    def __init__(self, max_k_hubs: int = 8):
        self.db = db_engine
        self.analytics = graph_analytics
        self.llm = llm_gateway
        self.tools = search_tools
        self.event_queue = event_queue
        self.max_k_hubs = max_k_hubs

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
        """Performs LLM pass across a passage chunk to extract atomic concept nodes and qualitative relation edges in the context of query and chat history."""
        system_prompt = load_prompt("passage_concept_extraction").format(
            doc_title=doc_title
        )
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
        """Consolidates raw passage concepts into document-specific canonical concepts with aggregated passage pointers."""
        if not raw_extracted_concepts:
            return {"concepts": [], "relations": []}

        system_prompt = load_prompt("consolidate_concepts").format(doc_title=doc_title)
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
        """Classifies user input into DIRECT_CONVERSATION, GRAPH_RETRIEVAL, or DOCUMENT_INGESTION and extracts ingestion target details (source_url, raw_text) in a single pass."""
        system_prompt = load_prompt("classify_intent")

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history[-4:])
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
            return {
                "intent": data.get("intent"),
                "source_url": data.get("source_url"),
                "raw_text": data.get("raw_text"),
            }
        except Exception:
            return {
                "intent": "DIRECT_CONVERSATION",
                "source_url": None,
                "raw_text": None,
            }

    async def process_user_message(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Central conversational entry point routing user input dynamically with error handling."""
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

            if intent == "DIRECT_CONVERSATION":
                async for event in self.execute_direct_conversation_flow(
                    query, chat_history, project_id=project_id
                ):
                    self.event_queue.push(project_id, event)
                    yield event
            elif intent == "DOCUMENT_INGESTION":
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
                    query, project_id=project_id
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

    async def execute_direct_conversation_flow(
        self,
        query: str,
        chat_history: List[Dict[str, str]],
        project_id: str = "global",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Direct conversational response without graph traversal overhead."""
        yield {
            "event": "conversation_start",
            "message": "Executive Orchestrator responding directly via conversational mode...",
            "timestamp": time.time(),
        }

        # Fetch last 15 system execution events for active project from in-memory queue
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

        base_prompt = load_prompt("direct_conversation")
        system_prompt = f"{base_prompt}{events_summary}"

        messages = [{"role": "system", "content": system_prompt}]
        if chat_history:
            messages.extend(chat_history)
        messages.append({"role": "user", "content": query})

        direct_response = self.llm.generate_chat_completion(messages)

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
        """Multi-Persona Parallel Retrieval over project-scoped concept hubs."""
        yield {
            "event": "persona_traversal_start",
            "message": f"Executive Orchestrator identifying dynamic concept hubs in project '{project_id}' for query: '{query}'",
            "timestamp": time.time(),
        }

        # Dynamically discover top concept hubs via rustworkx centrality in project scope
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
            async for event in self.execute_direct_conversation_flow(
                query, chat_history, project_id=project_id
            ):
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

            finding = dept.explore_and_retrieve(
                query=query, chat_history=chat_history, project_id=project_id
            )
            department_findings.append(finding)

            if finding.get("web_search_used"):
                yield {
                    "event": "persona_web_search",
                    "department_id": dept.department_id,
                    "search_query": f"{dept.hub_node.title} {query}",
                    "message": f"Persona '{dept.department_name}' executed DuckDuckGo web search tool.",
                    "timestamp": time.time(),
                }

            evt_active = {
                "event": "persona_traversal_active",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "traversed_node_ids": finding["traversed_node_ids"],
                "perspective_snippet": finding["perspective"][:150],
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, evt_active)
            yield evt_active

        # Push retrieval summary finding event into queue for direct conversation prompt awareness
        retrieval_summary_evt = {
            "event": "retrieval_summary",
            "message": f"Graph Retrieval completed across {len(active_departments)} concept departments for query: '{query}'",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, retrieval_summary_evt)

        # Delegate final assistant response turn directly to execute_direct_conversation_flow
        async for event in self.execute_direct_conversation_flow(
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
        """Multi-Pass Document Ingestion: Scrapes URL/payload, chunk passages, extracts atomic concepts, links concept hubs, & dispatches to direct conversation."""
        source_url = target_info.get("source_url")
        raw_payload = target_info.get("raw_text")

        # Step 1: Content Scraping & Title Extraction
        full_content = raw_payload
        title = None

        if source_url:
            doc_res = self.tools.fetch_document(source_url)
            if doc_res.get("content"):
                full_content = doc_res["content"]
                # Extract title from first markdown header (# Title) if available
                for line in full_content.splitlines():
                    if line.startswith("# "):
                        title = line[2:].strip()
                        break

        if not title:
            # Fallback to deriving title from raw_text payload (first non-empty line or snippet)
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
            "message": f"Executive Orchestrator invoking multi-pass document ingestion pipeline for '{title}'...",
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

        # Step 2: Passage Chunking (~500 token chunks)
        passage_chunks = self._chunk_text(full_content, chunk_size=1500)
        passage_ids = []
        for idx, chunk_str in enumerate(passage_chunks):
            p_id = f"pass_{uuid.uuid4().hex[:8]}"
            p_rec = PassageRecord(
                _id=p_id, doc_id=doc_id, chunk_index=idx, text_content=chunk_str
            )
            self.db.upsert_passage(p_rec)
            passage_ids.append(p_id)

        pass_chunk_evt = {
            "event": "passage_chunked",
            "doc_id": doc_id,
            "chunks_count": len(passage_ids),
            "message": f"Document '{title}' chunked into {len(passage_ids)} plain-text passage records.",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, pass_chunk_evt)
        yield pass_chunk_evt

        # Step 3: Multi-Pass Passage Concept Extraction
        raw_extracted_concepts: List[Dict[str, Any]] = []
        extracted_relations: List[Dict[str, Any]] = []

        for p_id, chunk_str in zip(passage_ids, passage_chunks):
            extraction = self._extract_concepts_from_passage(
                chunk_str, title, query, chat_history
            )
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

        # Step 4: In-Memory Concept Consolidation Across Passages
        # consolidated_concepts: [{idx: int, title: str, description: str, passage_ids: [str]}]
        # consolidated_relations: [{source_idx: int, target_idx: int, description: str}]
        consolidated_result = self.consolidate_extracted_concepts(
            raw_extracted_concepts, extracted_relations, title, query, chat_history
        )
        consolidated_concepts = consolidated_result.get("concepts", [])
        consolidated_relations = consolidated_result.get("relations", [])
        doc_description = consolidated_result.get(
            "doc_description", f"Consolidated knowledge document for '{title}'."
        )
        doc_type = consolidated_result.get("doc_type", "paper")

        proj_list = ["global"]
        if project_id and project_id != "global":
            proj_list.append(project_id)

        # Step 5: Save Root Media node and Intra-Document concept nodes & edges into DB prior to persona discovery
        concept_id_to_node: Dict[str, GraphNode] = {}
        for evt in self._create_intra_document_subgraph(
            doc_id=doc_id,
            doc_title=title,
            doc_description=doc_description,
            doc_type=doc_type,
            consolidated_concepts=consolidated_concepts,
            consolidated_relations=consolidated_relations,
            project_id=project_id,
            proj_list=proj_list,
            passage_ids=passage_ids,
            concept_id_to_node=concept_id_to_node,
        ):
            yield evt

        # Step 6: Discover Top Concept Hubs & Run Active Department Persona Ingestion to collect commands
        # top_hubs: [{
        #   id: str,
        #   node_type: str,
        #   title: str,
        #   description: str,
        #   passage_ids: [str],
        #   metadata: {str: any}
        # }]
        top_hubs = self.analytics.get_top_concept_hubs(
            project_id=project_id, max_k=self.max_k_hubs
        )
        active_departments = [
            DepartmentPersonaAgent(hub_node, score) for hub_node, score in top_hubs
        ]
        persona_command_results: List[Dict[str, Any]] = []
        for dept in active_departments:
            yield {
                "event": "persona_traversal_start",
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "hub_id": dept.hub_node.id,
                "message": f"Specialist Persona '{dept.hub_node.title}' evaluating newly consolidated concepts for global graph merging...",
                "timestamp": time.time(),
            }

            candidate_nodes = list(concept_id_to_node.values())
            ingest_res = dept.persona_ingestion(
                candidate_nodes, title, query, chat_history, project_id=project_id
            )
            # ingest_res: [{
            #     department_id: str,
            #     department_name: str,
            #     hub_node_id: str,
            #     traversed_node_ids: [str],
            #     commands: [{
            #       command_type: str,
            #       concept: {id: str, title: str, description: str, passage_ids: [str]},
            #       edge: {id: str, source_idx: str, target_idx: str, description: str}
            #     }],
            # }]
            persona_command_results.append(
                {
                    "dept": dept,
                    "commands": ingest_res.get("commands", []),
                }
            )

        # Step 7: Apply persona commands & global graph merging edits to DB in helper method
        for evt in self._apply_ingestion_graph_updates(
            doc_id=doc_id,
            doc_title=title,
            doc_description=doc_description,
            doc_type=doc_type,
            consolidated_concepts=consolidated_concepts,
            consolidated_relations=consolidated_relations,
            persona_command_results=persona_command_results,
            project_id=project_id,
            proj_list=proj_list,
            passage_ids=passage_ids,
            concept_id_to_node=concept_id_to_node,
        ):
            yield evt

        comp_evt = {
            "event": "tool_complete",
            "tool_name": "ingest_document_tool",
            "doc_id": doc_id,
            "created_nodes_count": len(consolidated_concepts),
            "passage_ids": passage_ids,
            "message": f"Successfully integrated document '{title}' with {len(consolidated_concepts)} concept nodes and {len(passage_ids)} passage pointers.",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, comp_evt)
        yield comp_evt

        # Step 7: Delegate final assistant response turn directly to execute_direct_conversation_flow
        ingest_query = f"I just ingested document '{title}'. Summarize the key additions and integrated graph concepts."
        async for event in self.execute_direct_conversation_flow(
            ingest_query, chat_history, project_id=project_id
        ):
            yield event

    def _run_multi_persona_debate(
        self,
        candidate_concept: Dict[str, Any],
        doc_title: str,
        proposals: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Runs a multi-persona debate turn when conflicting persona proposals exist for a candidate concept."""
        candidate_title = candidate_concept.get("title", "Untitled Concept")
        candidate_desc = candidate_concept.get("description", "")

        persona_proposals_payload = []
        for p in proposals:
            persona_proposals_payload.append(
                {
                    "persona_id": p["dept"].department_id,
                    "persona_name": p["dept"].department_name,
                    "hub_title": p["dept"].hub_node.title,
                    "command": p["cmd"],
                }
            )

        prompt_str = load_prompt("persona_ingestion_debate").format(
            doc_title=doc_title,
            candidate_title=candidate_title,
            candidate_description=candidate_desc,
            persona_proposals_json=json.dumps(persona_proposals_payload, indent=2),
        )

        messages = [
            {
                "role": "system",
                "content": "You are the Graph Synthesis Executive moderating a debate between domain specialist personas.",
            },
            {"role": "user", "content": prompt_str},
        ]

        try:
            res = llm_gateway.generate_chat_completion(
                messages,
                temperature=0.2,
                max_tokens=1024,
                response_format={"type": "json_object"},
                enable_reasoning=False,
            )
            data = json.loads(res)
            return data
        except Exception as e:
            print(f"[Multi-Persona Debate] Error during debate resolution: {e}")
            # Fallback to keeping candidate as a standalone merged edit if debate fails
            first_cmd = proposals[0]["cmd"]
            return {
                "resolution_type": "MERGE_SINGLE",
                "rationale": "Fallback merge resolution due to debate timeout.",
                "merged_target_node_id": first_cmd.get("existing_node_id"),
                "sub_concepts": [],
                "additional_edges": [],
            }

    def _create_intra_document_subgraph(
        self,
        doc_id: str,
        doc_title: str,
        doc_description: str,
        doc_type: str,
        consolidated_concepts: List[Dict[str, Any]],
        consolidated_relations: List[Dict[str, Any]],
        project_id: str,
        proj_list: List[str],
        passage_ids: List[str],
        concept_id_to_node: Optional[Dict[str, GraphNode]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Save root media node, concept nodes, and intra-document relations prior to persona discovery."""
        if concept_id_to_node is None:
            concept_id_to_node = {}

        # 0. Instantiate and save Root Media GraphNode representing the document
        doc_node = GraphNode(
            _id=doc_id,
            node_type=doc_type,
            title=doc_title,
            description=f"# {doc_title}\n\n## Executive Summary:\n{doc_description}",
            passage_ids=passage_ids,
            project_ids=proj_list,
            metadata={"status": "PRIMARY_ACTIVE"},
        )
        self.db.upsert_node(doc_node)
        root_evt = {
            "event": "concept_created",
            "persona_id": "orchestrator",
            "persona_name": "Ingestion Engine",
            "node_id": doc_id,
            "node_title": doc_title,
            "message": f"Root media graph node '{doc_title}' ({doc_type}) created.",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, root_evt)
        yield root_evt

        # Build index mapping helper for initial relation creation
        temp_idx_to_id: Dict[int, str] = {}
        for idx, c_data in enumerate(consolidated_concepts):
            c_id = f"concept_{uuid.uuid4().hex[:6]}"
            c_data["id"] = c_id
            c_data["idx"] = idx
            c_title = c_data["title"]
            passage_ptrs = c_data.get("passage_ids", [])
            c_node = GraphNode(
                _id=c_id,
                node_type="concept",
                title=c_title,
                description=f"# {c_title}\n{c_data.get('description', '')}",
                passage_ids=passage_ptrs,
                project_ids=proj_list,
                metadata={"status": "PRIMARY_ACTIVE"},
            )
            self.db.upsert_node(c_node)
            concept_id_to_node[c_id] = c_node
            temp_idx_to_id[idx] = c_id

            # Connect Root Media GraphNode -> Concept Node
            doc_edge_id = f"edge_{uuid.uuid4().hex[:8]}"
            doc_edge = GraphEdge(
                _id=doc_edge_id,
                source_id=doc_id,
                target_id=c_id,
                is_directional=True,
                description=f"Document '{doc_title}' presents concept '{c_title}'.",
                weight=1.0,
                project_ids=proj_list,
                status="PRIMARY_ACTIVE",
            )
            self.db.upsert_edge(doc_edge)

            node_evt = {
                "event": "concept_created",
                "persona_id": "orchestrator",
                "persona_name": "Ingestion Engine",
                "node_id": c_id,
                "node_title": c_title,
                "message": f"Intra-document concept '{c_title}' added to knowledge graph.",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, root_evt)
            yield node_evt

        # Save intra-document relations using temp_idx_to_id mapping
        for rel in consolidated_relations:
            src_id = temp_idx_to_id[rel["source_idx"]]
            tgt_id = temp_idx_to_id[rel["target_idx"]]
            edge_id = f"edge_{uuid.uuid4().hex[:8]}"
            direct_edge = GraphEdge(
                _id=edge_id,
                source_id=src_id,
                target_id=tgt_id,
                is_directional=True,
                description=rel.get(
                    "description",
                    f"Link from {src_id} to {tgt_id}",
                ),
                weight=1.0,
                project_ids=proj_list,
                status="PRIMARY_ACTIVE",
            )
            self.db.upsert_edge(direct_edge)

    def _apply_ingestion_graph_updates(
        self,
        doc_id: str,
        doc_title: str,
        doc_description: str,
        doc_type: str,
        consolidated_concepts: List[Dict[str, Any]],
        consolidated_relations: List[Dict[str, Any]],
        persona_command_results: List[Dict[str, Any]],
        project_id: str,
        proj_list: List[str],
        passage_ids: List[str],
        concept_id_to_node: Optional[Dict[str, GraphNode]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Apply all global graph persona reconciliation and merging edits to the DB using explicit node IDs."""
        if concept_id_to_node is None:
            concept_id_to_node = {
                c.get("id"): self.db.get_node(c.get("id"))
                for c in consolidated_concepts
                if c.get("id") and self.db.get_node(c.get("id"))
            }

        # 2. Parse and group persona commands by type and target node ID
        concept_edit_proposals = defaultdict(list)
        edge_commands = []
        node_delete_commands = []
        edge_delete_commands = []

        for res in persona_command_results:
            dept: DepartmentPersonaAgent = res["dept"]
            commands: List[Dict[str, Any]] = res["commands"]

            for cmd in commands:
                cmd_type = cmd.get("command_type")
                concept_data = cmd.get("concept", {})
                edge_data = cmd.get("edge", {})

                # Extract candidate or node reference
                c_ref = (
                    concept_data.get("id")
                    or cmd.get("candidate_id")
                    or cmd.get("candidate_idx")
                )
                e_src_ref = (
                    edge_data.get("source_idx")
                    or cmd.get("source_ref")
                    or cmd.get("source_id")
                )
                e_tgt_ref = (
                    edge_data.get("target_idx")
                    or cmd.get("target_ref")
                    or cmd.get("target_id")
                )

                if cmd_type == "CREATE_CONCEPT":
                    # Emit new standalone domain concept
                    c_title = concept_data.get("title", "New Domain Concept")
                    c_desc = concept_data.get("description", "")
                    c_passages = concept_data.get("passage_ids", passage_ids)
                    new_id = f"concept_{uuid.uuid4().hex[:6]}"
                    new_node = GraphNode(
                        _id=new_id,
                        node_type="concept",
                        title=c_title,
                        description=f"# {c_title}\n{c_desc}",
                        passage_ids=c_passages,
                        project_ids=proj_list,
                        metadata={"status": "PRIMARY_ACTIVE"},
                    )
                    self.db.upsert_node(new_node)
                elif cmd_type == "EDIT_CONCEPT":
                    target_id = concept_data.get("id") or cmd.get("existing_node_id")
                    target_desc = concept_data.get("description") or cmd.get(
                        "additional_text", ""
                    )
                    target_passages = concept_data.get("passage_ids", [])

                    # Standardize payload format for debate / reconciliation
                    std_cmd = {
                        "command_type": "EDIT_CONCEPT",
                        "existing_node_id": target_id,
                        "additional_text": target_desc,
                        "passage_ids": target_passages,
                    }

                    # Determine candidate node ID: check c_ref in concept_id_to_node, or match by candidate index/fallback
                    c_id = None
                    if isinstance(c_ref, str):
                        if c_ref in concept_id_to_node:
                            c_id = c_ref
                        else:
                            try:
                                c_idx = int(c_ref)
                                if c_idx < len(consolidated_concepts):
                                    c_id = consolidated_concepts[c_idx].get("id")
                            except ValueError:
                                pass
                    elif isinstance(c_ref, int) and c_ref < len(consolidated_concepts):
                        c_id = consolidated_concepts[c_ref].get("id")

                    if not c_id and consolidated_concepts:
                        c_id = consolidated_concepts[0].get("id")

                    if c_id:
                        concept_edit_proposals[c_id].append(
                            {"dept": dept, "cmd": std_cmd}
                        )

                elif cmd_type == "DELETE_CONCEPT":
                    del_id = concept_data.get("id") or cmd.get("node_id")
                    if del_id:
                        node_delete_commands.append(del_id)

                elif cmd_type in ("CONSTRUCT_EDGE", "EDIT_EDGE"):
                    edge_commands.append(
                        {
                            "dept": dept,
                            "cmd": {
                                "source_idx": e_src_ref,
                                "target_idx": e_tgt_ref,
                                "description": edge_data.get("description")
                                or cmd.get("description", ""),
                            },
                        }
                    )

                elif cmd_type == "DELETE_EDGE":
                    del_e_id = edge_data.get("id") or cmd.get("edge_id")
                    if del_e_id:
                        edge_delete_commands.append(del_e_id)

        # Execute DELETE_CONCEPT commands
        for del_id in node_delete_commands:
            self.db.delete_node(del_id)

        # Execute DELETE_EDGE commands
        for del_e_id in edge_delete_commands:
            self.db.delete_edge(del_e_id)

        # 3. Process EDIT_CONCEPT proposals per candidate concept via 2-path logic
        for candidate_concept in consolidated_concepts:
            c_id = candidate_concept.get("id")
            proposals = concept_edit_proposals.get(c_id, [])
            if not proposals:
                continue

            # Determine if proposals are conflicting (different target node IDs)
            unique_targets = set(
                p["cmd"].get("existing_node_id")
                for p in proposals
                if p["cmd"].get("existing_node_id")
            )

            if len(unique_targets) <= 1:
                # === PATH 1: NO CONFLICT ===
                # All personas agree on the same target or only one persona proposed a merge
                chosen = proposals[0]
                dept = chosen["dept"]
                cmd = chosen["cmd"]
                existing_id = cmd.get("existing_node_id")
                existing_node = self.db.get_node(existing_id) if existing_id else None
                if not existing_node:
                    continue

                temp_intra_node = concept_id_to_node.get(c_id) or self.db.get_node(c_id)

                if cmd.get("additional_text"):
                    existing_node.description += (
                        f"\n\n## Addition from '{doc_title}':\n{cmd['additional_text']}"
                    )
                for pid in cmd.get("passage_ids", []):
                    if pid not in existing_node.passage_ids:
                        existing_node.passage_ids.append(pid)
                self.db.upsert_node(existing_node)

                if temp_intra_node and temp_intra_node.id != existing_node.id:
                    temp_id = temp_intra_node.id
                    all_edges = self.db.get_edges()
                    for edge in all_edges:
                        if edge.source_id == temp_id or edge.target_id == temp_id:
                            new_src = (
                                existing_node.id
                                if edge.source_id == temp_id
                                else edge.source_id
                            )
                            new_tgt = (
                                existing_node.id
                                if edge.target_id == temp_id
                                else edge.target_id
                            )
                            if new_src != new_tgt:
                                rewired_edge = GraphEdge(
                                    _id=f"edge_{uuid.uuid4().hex[:8]}",
                                    source_id=new_src,
                                    target_id=new_tgt,
                                    is_directional=edge.is_directional,
                                    description=edge.description,
                                    weight=edge.weight,
                                    project_ids=edge.project_ids,
                                    status=edge.status,
                                )
                                self.db.upsert_edge(rewired_edge)
                            self.db.delete_edge(edge.id)
                    self.db.delete_node(temp_id)

                node_evt = {
                    "event": "concept_updated",
                    "persona_id": dept.department_id,
                    "persona_name": dept.department_name,
                    "node_id": existing_node.id,
                    "node_title": existing_node.title,
                    "message": f"Concept '{existing_node.title}' updated directly with consensus insights from '{doc_title}'.",
                    "timestamp": time.time(),
                }
                self.event_queue.push(project_id, node_evt)
                yield node_evt

            else:
                # === PATH 2: CONFLICT DETECTED -> MULTI-PERSONA DEBATE TURN ===
                debate_evt = {
                    "event": "persona_debate_start",
                    "candidate_title": candidate_concept.get("title"),
                    "conflicting_personas": [
                        p["dept"].department_name for p in proposals
                    ],
                    "message": f"Conflicting merge proposals detected for concept '{candidate_concept.get('title')}'. Initiating Multi-Persona Debate...",
                    "timestamp": time.time(),
                }
                self.event_queue.push(project_id, debate_evt)
                yield debate_evt

                debate_res = self._run_multi_persona_debate(
                    candidate_concept=candidate_concept,
                    doc_title=doc_title,
                    proposals=proposals,
                )

                resolution_type = debate_res.get("resolution_type", "MERGE_SINGLE")
                temp_intra_node = concept_id_to_node.get(c_id) or self.db.get_node(c_id)

                if resolution_type == "SUBDIVIDE":
                    # Debate outcome: Sub-divide concept into multiple refined sub-concepts
                    sub_concepts = debate_res.get("sub_concepts", [])
                    for sub in sub_concepts:
                        sub_title = sub.get(
                            "sub_title", f"{candidate_concept['title']} (Sub)"
                        )
                        sub_target_id = sub.get("target_node_id")

                        if sub_target_id and self.db.get_node(sub_target_id):
                            # Merge sub-concept into existing domain node
                            t_node = self.db.get_node(sub_target_id)
                            t_node.description += f"\n\n## Sub-concept from '{doc_title}':\n# {sub_title}\n{sub.get('description', '')}"
                            for pid in sub.get("passage_ids", passage_ids):
                                if pid not in t_node.passage_ids:
                                    t_node.passage_ids.append(pid)
                            self.db.upsert_node(t_node)
                        else:
                            # Create new sub-concept node
                            sub_id = f"concept_{uuid.uuid4().hex[:6]}"
                            sub_node = GraphNode(
                                _id=sub_id,
                                node_type="concept",
                                title=sub_title,
                                description=f"# {sub_title}\n{sub.get('description', '')}",
                                passage_ids=sub.get("passage_ids", passage_ids),
                                project_ids=proj_list,
                                metadata={"status": "PRIMARY_ACTIVE"},
                            )
                            self.db.upsert_node(sub_node)
                            # Link root media node to sub-concept
                            sub_edge = GraphEdge(
                                _id=f"edge_{uuid.uuid4().hex[:8]}",
                                source_id=doc_id,
                                target_id=sub_id,
                                is_directional=True,
                                description=f"Document '{doc_title}' presents sub-concept '{sub_title}'.",
                                weight=1.0,
                                project_ids=proj_list,
                                status="PRIMARY_ACTIVE",
                            )
                            self.db.upsert_edge(sub_edge)

                    if temp_intra_node:
                        self.db.delete_node(temp_intra_node.id)

                elif resolution_type == "MERGE_SINGLE":
                    target_id = (
                        debate_res.get("merged_target_node_id")
                        or list(unique_targets)[0]
                    )
                    target_node = self.db.get_node(target_id)
                    if target_node:
                        target_node.description += f"\n\n## Consensus Debate Insight from '{doc_title}':\n{candidate_concept.get('description', '')}"
                        for pid in candidate_concept.get("passage_ids", passage_ids):
                            if pid not in target_node.passage_ids:
                                target_node.passage_ids.append(pid)
                        self.db.upsert_node(target_node)

                        if temp_intra_node and temp_intra_node.id != target_node.id:
                            self.db.delete_node(temp_intra_node.id)

                # Process any additional bridge edges decided by the debate
                for add_edge in debate_res.get("additional_edges", []):
                    s_id = add_edge.get("source_idx") or add_edge.get("source_ref")
                    t_id = add_edge.get("target_idx") or add_edge.get("target_ref")
                    if s_id and t_id and s_id != t_id:
                        bridge_edge = GraphEdge(
                            _id=f"edge_{uuid.uuid4().hex[:8]}",
                            source_id=s_id,
                            target_id=t_id,
                            is_directional=True,
                            description=add_edge.get(
                                "description", "Cross-domain debate bridge edge."
                            ),
                            weight=1.0,
                            project_ids=proj_list,
                            status="PRIMARY_ACTIVE",
                        )
                        self.db.upsert_edge(bridge_edge)

                res_evt = {
                    "event": "persona_debate_complete",
                    "candidate_title": candidate_concept.get("title"),
                    "resolution_type": resolution_type,
                    "message": f"Multi-Persona Debate for '{candidate_concept.get('title')}' completed with resolution: {resolution_type}.",
                    "timestamp": time.time(),
                }
                self.event_queue.push(project_id, res_evt)
                yield res_evt

        # 4. Process collected CONSTRUCT_EDGE / EDIT_EDGE commands
        for item in edge_commands:
            cmd = item["cmd"]
            src_ref = cmd.get("source_idx")
            src_id = None
            if isinstance(src_ref, str):
                if src_ref in concept_id_to_node:
                    src_id = concept_id_to_node[src_ref].id
                elif self.db.get_node(src_ref):
                    src_id = src_ref
                else:
                    try:
                        s_idx = int(src_ref)
                        if s_idx < len(consolidated_concepts):
                            c_cand_id = consolidated_concepts[s_idx].get("id")
                            if c_cand_id and c_cand_id in concept_id_to_node:
                                src_id = concept_id_to_node[c_cand_id].id
                    except ValueError:
                        pass
            elif isinstance(src_ref, int) and src_ref < len(consolidated_concepts):
                c_cand_id = consolidated_concepts[src_ref].get("id")
                if c_cand_id and c_cand_id in concept_id_to_node:
                    src_id = concept_id_to_node[c_cand_id].id

            tgt_ref = cmd.get("target_idx")
            tgt_id = None
            if isinstance(tgt_ref, str):
                if tgt_ref in concept_id_to_node:
                    tgt_id = concept_id_to_node[tgt_ref].id
                elif self.db.get_node(tgt_ref):
                    tgt_id = tgt_ref
                else:
                    try:
                        t_idx = int(tgt_ref)
                        if t_idx < len(consolidated_concepts):
                            c_cand_id = consolidated_concepts[t_idx].get("id")
                            if c_cand_id and c_cand_id in concept_id_to_node:
                                tgt_id = concept_id_to_node[c_cand_id].id
                    except ValueError:
                        pass
            elif isinstance(tgt_ref, int) and tgt_ref < len(consolidated_concepts):
                c_cand_id = consolidated_concepts[tgt_ref].get("id")
                if c_cand_id and c_cand_id in concept_id_to_node:
                    tgt_id = concept_id_to_node[c_cand_id].id

            if src_id and tgt_id and src_id != tgt_id:
                edge_id = f"edge_{uuid.uuid4().hex[:8]}"
                new_edge = GraphEdge(
                    _id=edge_id,
                    source_id=src_id,
                    target_id=tgt_id,
                    is_directional=True,
                    description=cmd.get(
                        "description",
                        f"Link from {src_id} to {tgt_id}",
                    ),
                    weight=1.0,
                    project_ids=proj_list,
                    status="PRIMARY_ACTIVE",
                )
                self.db.upsert_edge(new_edge)

        summary_evt = {
            "event": "ingestion_completed",
            "doc_id": doc_id,
            "title": doc_title,
            "concepts_count": len(consolidated_concepts),
            "message": f"Document '{doc_title}' successfully ingested and merged into knowledge graph.",
            "timestamp": time.time(),
        }
        self.event_queue.push(project_id, summary_evt)
        yield summary_evt


orchestrator = ExecutiveOrchestrator()
