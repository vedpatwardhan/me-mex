#!/usr/bin/env python3
"""
Reset Script for Me-Mex Production/Development Database (`me-mex`).

Wipes all collections (nodes, edges, documents, passages, staging_sandbox,
chat_messages, projects) and re-seeds:
  1. Default ProjectWorkspace: `global` ("Global Master Graph")
  2. Primordial Universal Genesis Concept Node: `concept_genesis` ("Everything")

Usage:
  me-mex/.venv/bin/python3.14 me-mex/backend/reset_db.py
"""

import os
import sys

backend_dir = os.path.abspath(os.path.dirname(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.db import db_engine
from app.models import ProjectWorkspace, GraphNode
from app.services.event_queue import event_queue


def reset_database():
    print("[Me-Mex DB Reset] Initializing reset...")

    if db_engine.use_mongo:
        db = db_engine.db
        collections = [
            "nodes",
            "edges",
            "documents",
            "passages",
            "staging_sandbox",
            "chat_messages",
            "projects",
        ]
        for col in collections:
            count = db[col].count_documents({})
            db[col].delete_many({})
            print(f"  - Cleared '{col}': {count} documents removed.")
    else:
        db_engine.mem_nodes.clear()
        db_engine.mem_edges.clear()
        db_engine.mem_documents.clear()
        db_engine.mem_passages.clear()
        db_engine.mem_staging.clear()
        db_engine.mem_messages.clear()
        db_engine.mem_projects.clear()
        print("  - Cleared in-memory fallback stores.")

    event_queue.clear()
    print("  - Cleared in-memory event queues.")

    # 1. Re-seed default global Project Workspace
    global_proj = ProjectWorkspace(
        _id="global",
        name="Global Master Graph",
        description="Master superset database across all paradigms and literature.",
    )
    db_engine.upsert_project(global_proj)
    print("  + Seeded Project Workspace: 'global'")

    # 2. Re-seed single Primordial Universal Genesis Concept Node
    genesis_node = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        description="# Everything\nPrimordial universal knowledge anchor. High-level root concept connecting all domain paradigms and foundational literature.",
        metadata={
            "immutable": False,
            "is_genesis": True,
            "status": "PRIMARY_ACTIVE",
        },
        project_ids=["global"],
    )
    db_engine.upsert_node(genesis_node)
    print("  + Seeded Universal Genesis Concept Node: 'concept_genesis' ('Everything')")

    print("\n✅ Database 'me-mex' successfully reset to pristine Genesis state!")


if __name__ == "__main__":
    reset_database()
