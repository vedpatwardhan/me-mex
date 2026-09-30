import json
import uuid
import time
from collections import defaultdict
from typing import List, Dict, Any, Generator, Optional, Tuple
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

    def run_bilateral_persona_debate(
        self,
        persona_a: DepartmentPersonaAgent,
        persona_b: DepartmentPersonaAgent,
        persona_a_commands: List[Dict[str, Any]],
        persona_b_objections: List[Dict[str, Any]],
        doc_title: str,
        project_id: str = "global",
        max_turns: int = 3,
    ) -> Generator[Dict[str, Any], None, List[Dict[str, Any]]]:
        """Runs a dynamic multi-turn bilateral debate loop between conflicting personas until consensus or max turns."""
        debate_history: List[Dict[str, Any]] = []
        objections_context = [
            {
                "proposing_persona": persona_a.department_name,
                "proposed_commands": [c.get("command") for c in persona_a_commands],
                "objecting_persona": persona_b.department_name,
                "objections": persona_b_objections,
            }
        ]

        current_speaker = persona_a
        other_speaker = persona_b
        resolved_commands: List[Dict[str, Any]] = []

        for turn in range(1, max_turns + 1):
            turn_res = current_speaker.respond_to_debate_turn(
                opposing_persona_name=other_speaker.department_name,
                opposing_explored_nodes=other_speaker.last_explored_nodes
                or [other_speaker.hub_node],
                objections_context=objections_context,
                debate_history=debate_history,
                doc_title=doc_title,
                current_turn=turn,
                max_turns=max_turns,
            )

            turn_evt = {
                "event": "persona_debate_turn",
                "doc_title": doc_title,
                "turn": turn,
                "max_turns": max_turns,
                "speaker_persona_id": current_speaker.department_id,
                "speaker_persona_name": current_speaker.department_name,
                "opposing_persona_name": other_speaker.department_name,
                "turn_rationale": turn_res.get("turn_rationale", ""),
                "consensus_reached": turn_res.get("consensus_reached", False),
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, turn_evt)
            yield turn_evt

            turn_entry = {
                "turn": turn,
                "speaker": current_speaker.department_name,
                "rationale": turn_res.get("turn_rationale", ""),
                "consensus_reached": turn_res.get("consensus_reached", False),
                "proposed_resolved_commands": turn_res.get("resolved_commands", []),
            }
            debate_history.append(turn_entry)

            if turn_res.get("resolved_commands"):
                resolved_commands.extend(turn_res["resolved_commands"])

            if turn_res.get("consensus_reached", False):
                break

            current_speaker, other_speaker = other_speaker, current_speaker

        # Format resolved commands into flat execution format
        final_cmd_items = []
        for idx, r_cmd in enumerate(resolved_commands):
            # Parse command structure to standard flat item
            final_cmd_items.append(
                {
                    "command_id": f"debate_resolved_cmd_{idx}",
                    "department_id": persona_a.department_id,
                    "department_name": persona_a.department_name,
                    "dept": persona_a,
                    "command": {
                        "command_type": r_cmd.get("action")
                        or r_cmd.get("command_type", "EDIT_CONCEPT"),
                        "concept": r_cmd.get("concept", {}),
                        "edge": r_cmd.get("edge", {}),
                    },
                }
            )

        return final_cmd_items

    def run_multi_persona_debate(
        self,
        doc_title: str,
        proposals: List[Dict[str, Any]],
        persona_objections: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Backward compatibility multi-persona debate pass."""
        prompt_str = load_prompt("persona_ingestion_debate").format(
            my_persona_name="Executive Moderator",
            opposing_persona_name="Conflicting Personas",
            doc_title=doc_title,
            my_explored_json="[]",
            opposing_explored_json="[]",
            objections_context_json=json.dumps(persona_objections or [], indent=2),
            debate_history_json="[]",
            current_turn=1,
            max_turns=1,
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
            first_cmd = proposals[0]["cmd"] if proposals else {}
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

        # 4. Process Conflicting Commands via Bilateral Multi-Persona Debate Engine
        if conflicting_commands:
            conflicting_personas = list(
                set(item["department_name"] for item in conflicting_commands)
            )
            debate_evt = {
                "event": "persona_debate_start",
                "candidate_title": doc_title,
                "conflicting_personas": conflicting_personas,
                "message": f"Conflicting persona proposals detected for document '{doc_title}'. Initiating Bilateral Multi-Persona Debates...",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, debate_evt)
            yield debate_evt

            # Build objection lookup by command_id
            cmd_to_objections: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for o in all_objections:
                cid = o.get("command_id")
                if cid:
                    cmd_to_objections[cid].append(o)

            # Group conflicting commands into persona pair clusters (Proposer, Objector)
            pair_clusters: Dict[Tuple[str, str], Dict[str, Any]] = {}
            for item in conflicting_commands:
                cid = item["command_id"]
                dept_a: DepartmentPersonaAgent = item["dept"]
                objs = cmd_to_objections.get(cid, [])

                for obj in objs:
                    obj_persona_name = obj.get("objecting_persona")
                    # Find objecting persona instance from persona_command_results
                    dept_b = next(
                        (
                            r["dept"]
                            for r in persona_command_results
                            if r["dept"].department_name == obj_persona_name
                        ),
                        None,
                    )
                    if dept_b and dept_a.department_id != dept_b.department_id:
                        # Canonical symmetric pair key (sorted ID tuple) to merge bidirectional objections into the same room
                        p1, p2 = sorted([dept_a, dept_b], key=lambda d: d.department_id)
                        pair_key = (p1.department_id, p2.department_id)
                        if pair_key not in pair_clusters:
                            pair_clusters[pair_key] = {
                                "persona_a": p1,
                                "persona_b": p2,
                                "commands_a": [],
                                "objections_b": [],
                            }
                        pair_clusters[pair_key]["commands_a"].append(item)
                        pair_clusters[pair_key]["objections_b"].append(obj)

            resolved_debate_commands: List[Dict[str, Any]] = []

            for pair_key, cluster in pair_clusters.items():
                p_a = cluster["persona_a"]
                p_b = cluster["persona_b"]
                cmds_a = cluster["commands_a"]
                objs_b = cluster["objections_b"]

                # Execute bilateral debate turn generator
                debate_gen = self.run_bilateral_persona_debate(
                    persona_a=p_a,
                    persona_b=p_b,
                    persona_a_commands=cmds_a,
                    persona_b_objections=objs_b,
                    doc_title=doc_title,
                    project_id=project_id,
                    max_turns=3,
                )

                pair_resolved_cmds = []
                try:
                    while True:
                        turn_evt = next(debate_gen)
                        yield turn_evt
                except StopIteration as stop:
                    pair_resolved_cmds = stop.value or []

                resolved_debate_commands.extend(pair_resolved_cmds)

            res_evt = {
                "event": "persona_debate_complete",
                "candidate_title": doc_title,
                "resolution_type": "BILATERAL_CONSENSUS",
                "message": f"Bilateral Multi-Persona Debates for document '{doc_title}' completed.",
                "timestamp": time.time(),
            }
            self.event_queue.push(project_id, res_evt)
            yield res_evt

            # Execute all resolved consensus commands against DB
            for item in resolved_debate_commands:
                evt = self.execute_single_command(
                    item=item, doc_title=doc_title, proj_list=proj_list
                )
                if evt:
                    yield evt

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
