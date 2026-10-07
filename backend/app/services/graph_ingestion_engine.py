"""
Graph Ingestion & Command Execution Engine: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 4:
- Executes independent, zero-consensus graph modifications proposed by Specialist Personas.
- Enforces strict Node Mutability Hierarchy:
    - Root Nodes (`ROOT`) and Intra-Document Concepts (`metadata.immutable = True`) are completely IMMUTABLE.
      Direct mutations (`EDIT_CONCEPT`, `DELETE_CONCEPT`, `SPLIT_CONCEPT`) targeting immutable nodes are strictly blocked.
    - Persona-created Domain Hubs and Intermediate nodes (`metadata.immutable = False`) are MUTABLE.
- Processes actions (`CONNECT_DIRECT`, `CREATE_INTERMEDIATE`, `EDIT_CONCEPT` on mutable nodes, `SPLIT_CONCEPT` on mutable nodes) directly.
- Multi-persona debates and consensus resolution loops have been completely deprecated and removed.
"""

import json
import uuid
import time
from typing import List, Dict, Any, Generator, Optional
from app.db import db_engine
from app.models import (
    GraphNode,
    GraphEdge,
)
from app.services.event_queue import event_queue
from app.services.llm_gateway import llm_gateway


class GraphIngestionEngine:
    """Service handling zero-consensus independent command execution and node mutability enforcement."""

    def __init__(self):
        self.db = db_engine
        self.llm = llm_gateway
        self.event_queue = event_queue

    def execute_single_command(
        self,
        item: Dict[str, Any],
        doc_title: str,
        proj_list: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Executes a single persona command against the MongoDB database, enforcing node mutability rules.
        """
        action = item.get("action") or item.get("command_type")
        dept_name = item.get("department_name", "Ingestion Engine")

        # 1. Action: CREATE_EDGE / CONNECT_DIRECT (Connect concepts with qualitative relation edge)
        if action in ["CREATE_EDGE", "CONNECT_DIRECT", "CONSTRUCT_EDGE"]:
            edge_data = item.get("edge", {})
            src_id = edge_data.get("source_id")
            tgt_id = edge_data.get("target_id")
            if src_id and tgt_id:
                edge_id = f"edge_{uuid.uuid4().hex[:8]}"
                edge_obj = GraphEdge(
                    _id=edge_id,
                    source_id=src_id,
                    target_id=tgt_id,
                    description=edge_data.get("description", "Related concept link"),
                    project_ids=proj_list,
                )
                self.db.upsert_edge(edge_obj)
                return {
                    "event": "node_touched",
                    "persona_name": dept_name,
                    "node_id": tgt_id,
                    "message": f"Connected concept '{src_id}' -> '{tgt_id}' ({edge_data.get('description', '')}).",
                    "timestamp": time.time(),
                }

        # 2. Action: CREATE_INTERMEDIATE (Create new mutable domain bridge concept)
        elif action in ["CREATE_INTERMEDIATE", "CREATE_CONCEPT"]:
            concept_data = item.get("concept", {})
            c_title = concept_data.get("title")
            if c_title:
                c_id = f"concept_{uuid.uuid4().hex[:8]}"
                new_node = GraphNode(
                    _id=c_id,
                    node_type="CONCEPT",
                    title=c_title,
                    description=concept_data.get("description", ""),
                    passage_ids=concept_data.get("passage_ids", []),
                    project_ids=proj_list,
                    metadata={
                        "immutable": False,
                        "status": "PRIMARY_ACTIVE",
                    },  # Mutable domain bridge
                )
                self.db.upsert_node(new_node)

                # Connect associated edges for the intermediate node
                for edge_info in item.get("edges", []):
                    edge_id = f"edge_{uuid.uuid4().hex[:8]}"
                    src = edge_info.get("source_id", c_id)
                    tgt = edge_info.get("target_id", c_id)
                    edge_obj = GraphEdge(
                        _id=edge_id,
                        source_id=src,
                        target_id=tgt,
                        description=edge_info.get("description", "Bridge relationship"),
                        project_ids=proj_list,
                    )
                    self.db.upsert_edge(edge_obj)

                return {
                    "event": "node_touched",
                    "persona_name": dept_name,
                    "node_id": c_id,
                    "message": f"Created intermediate domain concept '{c_title}'.",
                    "timestamp": time.time(),
                }

        # 3. Action: EDIT_CONCEPT (Mutate existing mutable domain concept)
        elif action == "EDIT_CONCEPT":
            concept_data = item.get("concept", {})
            target_id = concept_data.get("id")
            if target_id:
                target_node = self.db.get_node(target_id)
                # IMMUTABILITY SAFETY CHECK: Block edits targeting immutable nodes
                if target_node and target_node.is_immutable:
                    print(
                        f"[{dept_name}] MUTABILITY BLOCK: Cannot edit immutable node '{target_id}'."
                    )
                    return None

                if target_node:
                    target_node.title = concept_data.get("title", target_node.title)
                    target_node.description = concept_data.get(
                        "description", target_node.description
                    )
                    target_node.updated_at = time.time()
                    self.db.upsert_node(target_node)
                    return {
                        "event": "node_touched",
                        "persona_name": dept_name,
                        "node_id": target_id,
                        "message": f"Edited mutable domain concept '{target_node.title}'.",
                        "timestamp": time.time(),
                    }

        # 4. Action: SPLIT_CONCEPT (Non-destructive intermediate subdivision & re-wiring)
        elif action == "SPLIT_CONCEPT":
            concept_id = item.get("concept_id") or item.get("concept", {}).get("id")
            if concept_id:
                target_node = self.db.get_node(concept_id)
                # IMMUTABILITY SAFETY CHECK: Block splitting immutable nodes
                if target_node and target_node.is_immutable:
                    print(
                        f"[{dept_name}] MUTABILITY BLOCK: Cannot split immutable node '{concept_id}'."
                    )
                    return None

                sub_concepts = item.get("sub_concepts", [])
                rewired_edges = item.get("rewired_edges", [])
                if target_node and sub_concepts:
                    # PRESERVE ORIGINAL HUB: Target node remains as umbrella concept node!
                    sub_alias_map: Dict[str, str] = {}

                    # Insert newly created sub-concept nodes & connect to original hub
                    for sub in sub_concepts:
                        new_sub_id = f"concept_{uuid.uuid4().hex[:8]}"
                        alias = sub.get("sub_id_alias")
                        if alias:
                            sub_alias_map[alias] = new_sub_id

                        sub_node = GraphNode(
                            _id=new_sub_id,
                            node_type="CONCEPT",
                            title=sub.get("title", "Split Sub-Concept"),
                            description=sub.get("description", ""),
                            passage_ids=sub.get("passage_ids", target_node.passage_ids),
                            project_ids=proj_list,
                            metadata={"immutable": False, "sub_of_hub": concept_id},
                        )
                        self.db.upsert_node(sub_node)

                        # Link sub-concept directly to original target concept hub
                        hub_edge = GraphEdge(
                            _id=f"edge_{uuid.uuid4().hex[:8]}",
                            source_id=new_sub_id,
                            target_id=concept_id,
                            description="SUBSET_OF",
                            project_ids=proj_list,
                        )
                        self.db.upsert_edge(hub_edge)

                    # Re-wire neighbor edges to target the new sub-concepts
                    for rewired in rewired_edges:
                        neighbor_id = rewired.get("neighbor_id")
                        sub_alias = rewired.get("connect_to_sub_alias")
                        target_sub_id = sub_alias_map.get(sub_alias)
                        if neighbor_id and target_sub_id:
                            rewired_edge = GraphEdge(
                                _id=f"edge_{uuid.uuid4().hex[:8]}",
                                source_id=neighbor_id,
                                target_id=target_sub_id,
                                description=rewired.get("relation_type", "RELEVANT_TO"),
                                project_ids=proj_list,
                            )
                            self.db.upsert_edge(rewired_edge)

                    return {
                        "event": "node_touched",
                        "persona_name": dept_name,
                        "node_id": concept_id,
                        "message": (
                            f"Subdivided concept hub '{target_node.title}' into "
                            f"{len(sub_concepts)} intermediate sub-concepts."
                        ),
                        "timestamp": time.time(),
                    }

        return None

    def process_persona_ingestion_commands(
        self,
        persona_command_results: List[Dict[str, Any]],
        doc_id: str,
        doc_title: str,
        consolidated_concepts: List[Dict[str, Any]],
        project_id: str = "global",
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Processes persona ingestion and reorganization commands independently without consensus debate.
        """
        proj_list = [project_id] if project_id != "global" else ["global"]

        # Collect flat sequence of commands from all personas
        for res in persona_command_results:
            dept_name = res.get("department_name", "Ingestion Specialist")
            commands = res.get("commands", [])

            for cmd in commands:
                cmd_item = {
                    "department_name": dept_name,
                    "action": cmd.get("action") or cmd.get("command_type"),
                    "concept": cmd.get("concept"),
                    "concept_id": cmd.get("concept_id"),
                    "sub_concepts": cmd.get("sub_concepts"),
                    "edge": cmd.get("edge"),
                    "edges": cmd.get("edges"),
                }
                evt = self.execute_single_command(
                    item=cmd_item, doc_title=doc_title, proj_list=proj_list
                )
                if evt:
                    self.event_queue.push(project_id, evt)
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
