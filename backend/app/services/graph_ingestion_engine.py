import json
import uuid
import time
from typing import List, Dict, Any, Generator, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
)
from app.agents.department_persona import (
    DepartmentPersonaAgent,
)
from app.services.event_queue import event_queue
from app.services.llm_gateway import llm_gateway
from app.prompts import load_prompt


class GraphIngestionEngine:
    """Service handling zero-mutation command collection, persona objection gathering, multi-persona debate resolution, and DB graph mutations."""

    def __init__(self):
        self.db = db_engine
        self.llm = llm_gateway
        self.event_queue = event_queue

    def run_multi_persona_debate(
        self,
        doc_title: str,
        proposals: List[Dict[str, Any]],
        persona_objections: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs a multi-persona debate turn when conflicting persona proposals exist."""
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
            persona_proposals_json=json.dumps(persona_proposals_payload, indent=2),
            persona_objections_json=json.dumps(persona_objections or [], indent=2),
        )

        messages = [
            {
                "role": "system",
                "content": "You are the Graph Synthesis Executive moderating a debate between domain specialist personas.",
            },
            {"role": "user", "content": prompt_str},
        ]

        try:
            res = self.llm.generate_chat_completion(
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
                "merged_target_node_id": first_cmd.get("id"),
                "sub_concepts": [],
                "additional_edges": [],
            }

    def create_intra_document_subgraph(
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
        concept_id_to_node: Dict[str, GraphNode],
    ) -> Generator[Dict[str, Any], None, None]:
        """Save root media node, concept nodes, and intra-document relations prior to persona discovery."""

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
            self.event_queue.push(project_id, node_evt)
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

    def collect_persona_commands(
        self,
        persona_command_results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Parse & collect all raw commands across personas indexed with command_id without DB writes."""
        all_commands_flat = []
        cmd_counter = 0

        for res in persona_command_results:
            dept: DepartmentPersonaAgent = res["dept"]
            commands: List[Dict[str, Any]] = res.get("commands", [])

            for cmd in commands:
                cmd_id = f"cmd_{cmd_counter}"
                cmd_counter += 1
                all_commands_flat.append(
                    {
                        "command_id": cmd_id,
                        "department_id": dept.department_id,
                        "department_name": dept.department_name,
                        "dept": dept,
                        "command": cmd,
                    }
                )

        return all_commands_flat

    def collect_persona_objections(
        self,
        all_commands_flat: List[Dict[str, Any]],
        persona_command_results: List[Dict[str, Any]],
        doc_title: str,
        concept_id_to_node: Dict[str, GraphNode],
    ) -> List[Dict[str, Any]]:
        """LLM Pass: Ask each active persona to review all proposed commands and flag objections."""
        all_objections: List[Dict[str, Any]] = []
        candidate_nodes_list = list(concept_id_to_node.values())

        for res in persona_command_results:
            dept: DepartmentPersonaAgent = res["dept"]
            explored_subgraph_nodes = res.get("subgraph_nodes", [])
            objs = dept.evaluate_command_objections(
                all_persona_commands=all_commands_flat,
                doc_title=doc_title,
                candidate_nodes=candidate_nodes_list,
                explored_nodes=explored_subgraph_nodes,
            )
            if objs:
                for o in objs:
                    o["objecting_persona"] = dept.department_name
                    all_objections.append(o)
        return all_objections

    def execute_single_command(
        self, item: Dict[str, Any], doc_title: str, proj_list: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Executes a single non-conflicting command against the DB."""
        dept: DepartmentPersonaAgent = item["dept"]
        cmd: Dict[str, Any] = item["command"]
        cmd_type = cmd.get("command_type") or cmd.get("action")
        concept_data = cmd.get("concept") or {}
        edge_data = cmd.get("edge") or {}

        if cmd_type == "CREATE_CONCEPT":
            c_title = concept_data["title"]
            c_desc = concept_data["description"]
            c_passages = concept_data["passage_ids"]
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
            return {
                "event": "concept_created",
                "persona_id": dept.department_id,
                "persona_name": dept.department_name,
                "node_id": new_id,
                "node_title": c_title,
                "message": f"New domain concept '{c_title}' created by {dept.department_name}.",
                "timestamp": time.time(),
            }

        elif cmd_type == "EDIT_CONCEPT":
            target_id = concept_data["id"]
            existing_node = self.db.get_node(target_id)
            existing_node.title = concept_data["title"]
            existing_node.description += (
                f"\n\n## Addition from '{doc_title}':\n{concept_data['description']}"
            )
            for pid in concept_data["passage_ids"]:
                if pid not in existing_node.passage_ids:
                    existing_node.passage_ids.append(pid)
            self.db.upsert_node(existing_node)
            return {
                "event": "concept_updated",
                "persona_id": dept.department_id,
                "persona_name": dept.department_name,
                "node_id": existing_node.id,
                "node_title": existing_node.title,
                "message": f"Concept '{existing_node.title}' updated directly by {dept.department_name}.",
                "timestamp": time.time(),
            }

        elif cmd_type == "DELETE_CONCEPT":
            del_id = concept_data["id"]
            self.db.delete_node(del_id)

        elif cmd_type in ("CONSTRUCT_EDGE", "EDIT_EDGE"):
            src_id = edge_data["source_id"]
            tgt_id = edge_data["target_id"]
            if src_id and tgt_id and src_id != tgt_id:
                edge_id = f"edge_{uuid.uuid4().hex[:8]}"
                new_edge = GraphEdge(
                    _id=edge_id,
                    source_id=src_id,
                    target_id=tgt_id,
                    is_directional=True,
                    description=edge_data.get(
                        "description", f"Link from {src_id} to {tgt_id}"
                    ),
                    weight=1.0,
                    project_ids=proj_list,
                    status="PRIMARY_ACTIVE",
                )
                self.db.upsert_edge(new_edge)

        elif cmd_type == "DELETE_EDGE":
            del_e_id = edge_data.get("id")
            if del_e_id:
                self.db.delete_edge(del_e_id)

        return None

    def apply_ingestion_graph_updates(
        self,
        doc_id: str,
        doc_title: str,
        consolidated_concepts: List[Dict[str, Any]],
        persona_command_results: List[Dict[str, Any]],
        project_id: str,
        proj_list: List[str],
        passage_ids: List[str],
        concept_id_to_node: Dict[str, GraphNode],
    ) -> Generator[Dict[str, Any], None, None]:
        """Apply all global graph persona reconciliation and merging edits to the DB using explicit node IDs without upfront mutations."""

        # 1. Zero-Mutation Collection Phase: Parse & index all raw commands across personas
        all_commands_flat = self.collect_persona_commands(persona_command_results)

        # 2. LLM Step: Persona Command Objection Review Pass
        all_objections = self.collect_persona_objections(
            all_commands_flat, persona_command_results, doc_title, concept_id_to_node
        )

        # Identify objected command IDs vs non-conflicting (unobjected) commands
        objected_cmd_ids = set(
            o.get("command_id") for o in all_objections if o.get("command_id")
        )

        non_conflicting_commands = [
            item
            for item in all_commands_flat
            if item["command_id"] not in objected_cmd_ids
        ]
        conflicting_commands = [
            item for item in all_commands_flat if item["command_id"] in objected_cmd_ids
        ]

        # 3. Execute Non-Conflicting (Unobjected) Commands Immediately
        for item in non_conflicting_commands:
            evt = self.execute_single_command(
                item=item, doc_title=doc_title, proj_list=proj_list
            )
            if evt:
                yield evt

        # 4. Process Conflicting Commands via Multi-Persona Debate Engine
        if conflicting_commands:
            conflicting_personas = list(
                set(item["department_name"] for item in conflicting_commands)
            )
            debate_evt = {
                "event": "persona_debate_start",
                "candidate_title": doc_title,
                "conflicting_personas": conflicting_personas,
                "message": f"Conflicting persona proposals detected for document '{doc_title}'. Initiating Multi-Persona Debate...",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, debate_evt)
            yield debate_evt

            proposals_payload = [
                {"dept": item["dept"], "cmd": item["command"]}
                for item in conflicting_commands
            ]

            debate_res = self.run_multi_persona_debate(
                doc_title=doc_title,
                proposals=proposals_payload,
                persona_objections=all_objections,
            )

            resolution_type = debate_res.get("resolution_type", "MERGE_SINGLE")
            rationale = debate_res.get(
                "rationale", f"Consensus debate insight from '{doc_title}'"
            )

            if resolution_type == "SUBDIVIDE":
                sub_concepts = debate_res.get("sub_concepts", [])
                for sub in sub_concepts:
                    sub_title = sub.get("sub_title", f"{doc_title} (Sub)")
                    sub_target_id = sub.get("target_node_id")

                    if sub_target_id and self.db.get_node(sub_target_id):
                        t_node = self.db.get_node(sub_target_id)
                        t_node.description += f"\n\n## Sub-concept from '{doc_title}':\n# {sub_title}\n{sub.get('description', '')}"
                        for pid in sub.get("passage_ids", passage_ids):
                            if pid not in t_node.passage_ids:
                                t_node.passage_ids.append(pid)
                        self.db.upsert_node(t_node)
                    else:
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

            elif resolution_type == "MERGE_SINGLE":
                target_id = debate_res.get("merged_target_node_id")
                if target_id and self.db.get_node(target_id):
                    target_node = self.db.get_node(target_id)
                    target_node.description += f"\n\n## Consensus Debate Insight from '{doc_title}':\n{rationale}"
                    for pid in passage_ids:
                        if pid not in target_node.passage_ids:
                            target_node.passage_ids.append(pid)
                    self.db.upsert_node(target_node)

            for add_edge in debate_res.get("additional_edges", []):
                s_id = (
                    add_edge.get("source_id")
                    or add_edge.get("source_ref")
                    or add_edge.get("source_idx")
                )
                t_id = (
                    add_edge.get("target_id")
                    or add_edge.get("target_ref")
                    or add_edge.get("target_idx")
                )
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
                "candidate_title": doc_title,
                "resolution_type": resolution_type,
                "message": f"Multi-Persona Debate for document '{doc_title}' completed with resolution: {resolution_type}.",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, res_evt)
            yield res_evt

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


graph_ingestion_engine = GraphIngestionEngine()
