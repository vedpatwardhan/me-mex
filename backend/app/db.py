import os
import time
from typing import Dict, List, Optional, Any
from app.models import (
    GraphNode,
    GraphEdge,
    DocumentRecord,
    PassageRecord,
    MacroDocumentRecord,
    StagingRecord,
    ProjectWorkspace,
    ChatMessageRecord,
    ProjectEventRecord,
)

# Try PyMongo import, fall back gracefully if MongoDB server is offline/not installed
try:
    import pymongo
    from pymongo import MongoClient

    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

from app.config import settings

# MongoDB Connection Configuration
MONGO_URI = settings.MONGO_URI
DB_NAME = settings.DB_NAME


class GraphMemexDatabase:
    """Hybrid MongoDB Database Engine with in-memory fallback for local execution."""

    @property
    def db(self):
        if self.use_mongo and self.client:
            return self.client[settings.DB_NAME]
        return None

    def __init__(self):
        self.use_mongo = False
        self.client = None

        # In-memory fallbacks
        self.mem_documents: Dict[str, DocumentRecord] = {}
        self.mem_passages: Dict[str, PassageRecord] = {}
        self.mem_nodes: Dict[str, GraphNode] = {}
        self.mem_edges: Dict[str, GraphEdge] = {}
        self.mem_staging: Dict[str, StagingRecord] = {}
        self.mem_projects: Dict[str, ProjectWorkspace] = {}
        self.mem_messages: Dict[str, ChatMessageRecord] = {}
        self.mem_events: Dict[str, List[ProjectEventRecord]] = {}

        if HAS_PYMONGO:
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
                self.client.admin.command("ping")
                self.use_mongo = True
                print(
                    f"[Database] Connected to MongoDB at {MONGO_URI}, DB: {settings.DB_NAME}"
                )
            except Exception as e:
                print(
                    f"[Database] MongoDB unavailable ({e}). Running in-memory fallback mode."
                )
                self.use_mongo = False
        else:
            print("[Database] PyMongo not installed. Running in-memory fallback mode.")

        self._seed_initial_data()

    def _seed_initial_data(self):
        """Seed default global project workspace and primordial Universal Genesis Concept Node ('Everything')."""
        if not self.get_projects():
            global_proj = ProjectWorkspace(
                _id="global",
                name="Global Master Graph",
                description="Master superset database across all paradigms and literature.",
            )
            self.upsert_project(global_proj)

        if not self.get_nodes():
            genesis_node = GraphNode(
                _id="concept_genesis",
                node_type="concept",
                title="Everything",
                description=(
                    "# Everything\nPrimordial universal knowledge anchor. High-level "
                    "root concept connecting all domain paradigms and foundational "
                    "literature."
                ),
                metadata={
                    "immutable": False,
                    "is_genesis": True,
                    "status": "PRIMARY_ACTIVE",
                },
                project_ids=["global"],
            )
            self.upsert_node(genesis_node)

    def upsert_node(self, node: GraphNode):
        if self.use_mongo:
            self.db.nodes.update_one(
                {"_id": node.id}, {"$set": node.model_dump(by_alias=True)}, upsert=True
            )
        else:
            self.mem_nodes[node.id] = node

    def get_nodes(self, project_id: Optional[str] = None) -> List[GraphNode]:
        if self.use_mongo:
            query = (
                {"project_ids": project_id}
                if project_id and project_id != "global"
                else {}
            )
            docs = list(self.db.nodes.find(query))
            return [GraphNode(**d) for d in docs]
        else:
            if project_id and project_id != "global":
                return [
                    n for n in self.mem_nodes.values() if project_id in n.project_ids
                ]
            return list(self.mem_nodes.values())

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        if self.use_mongo:
            doc = self.db.nodes.find_one({"_id": node_id})
            return GraphNode(**doc) if doc else None
        else:
            return self.mem_nodes.get(node_id)

    # --- Edge Operations ---
    def upsert_edge(self, edge: GraphEdge):
        if self.use_mongo:
            self.db.edges.update_one(
                {"_id": edge.id}, {"$set": edge.model_dump(by_alias=True)}, upsert=True
            )
        else:
            self.mem_edges[edge.id] = edge

    def get_edges(self, project_id: Optional[str] = None) -> List[GraphEdge]:
        if self.use_mongo:
            query = (
                {"project_ids": project_id}
                if project_id and project_id != "global"
                else {}
            )
            docs = list(self.db.edges.find(query))
            return [GraphEdge(**d) for d in docs]
        else:
            if project_id and project_id != "global":
                return [
                    e for e in self.mem_edges.values() if project_id in e.project_ids
                ]
            return list(self.mem_edges.values())

    def delete_node(self, node_id: str):
        if self.use_mongo:
            self.db.nodes.delete_one({"_id": node_id})
        else:
            self.mem_nodes.pop(node_id, None)

    def delete_edge(self, edge_id: str):
        if self.use_mongo:
            self.db.edges.delete_one({"_id": edge_id})
        else:
            self.mem_edges.pop(edge_id, None)

    # --- Project Operations ---
    def upsert_project(self, project: ProjectWorkspace):
        if self.use_mongo:
            self.db.projects.update_one(
                {"_id": project.id},
                {"$set": project.model_dump(by_alias=True)},
                upsert=True,
            )
        else:
            self.mem_projects[project.id] = project

    def get_projects(self) -> List[ProjectWorkspace]:
        if self.use_mongo:
            docs = list(self.db.projects.find({}))
            return [ProjectWorkspace(**d) for d in docs]
        else:
            return list(self.mem_projects.values())

    def get_project(self, project_id: str) -> Optional[ProjectWorkspace]:
        if self.use_mongo:
            doc = self.db.projects.find_one({"_id": project_id})
            return ProjectWorkspace(**doc) if doc else None
        else:
            return self.mem_projects.get(project_id)

    # --- Passage Operations ---
    def upsert_passage(self, passage: PassageRecord):
        if self.use_mongo:
            self.db.passages.update_one(
                {"_id": passage.id},
                {"$set": passage.model_dump(by_alias=True)},
                upsert=True,
            )
        else:
            self.mem_passages[passage.id] = passage

    def get_passages(self, passage_ids: List[str]) -> List[PassageRecord]:
        if self.use_mongo:
            docs = list(self.db.passages.find({"_id": {"$in": passage_ids}}))
            return [PassageRecord(**d) for d in docs]
        else:
            return [
                self.mem_passages[pid]
                for pid in passage_ids
                if pid in self.mem_passages
            ]

    # --- Document Operations ---
    def upsert_document(self, doc: DocumentRecord):
        if self.use_mongo:
            self.db.documents.update_one(
                {"_id": doc.id}, {"$set": doc.model_dump(by_alias=True)}, upsert=True
            )
        else:
            self.mem_documents[doc.id] = doc

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        if self.use_mongo:
            d = self.db.documents.find_one({"_id": doc_id})
            return DocumentRecord(**d) if d else None
        else:
            return self.mem_documents.get(doc_id)

    def get_documents(self) -> List[DocumentRecord]:
        if self.use_mongo:
            docs = list(self.db.documents.find({}))
            return [DocumentRecord(**d) for d in docs]
        else:
            return list(self.mem_documents.values())

    # --- Staging Operations ---
    def upsert_staging(self, stage: StagingRecord):
        if self.use_mongo:
            self.db.staging_sandbox.update_one(
                {"_id": stage.id},
                {"$set": stage.model_dump(by_alias=True)},
                upsert=True,
            )
        else:
            self.mem_staging[stage.id] = stage

    def get_staging(self, stage_id: str) -> Optional[StagingRecord]:
        if self.use_mongo:
            d = self.db.staging_sandbox.find_one({"_id": stage_id})
            return StagingRecord(**d) if d else None
        else:
            return self.mem_staging.get(stage_id)

    # --- Chat Message Operations ---
    def upsert_message(self, msg: ChatMessageRecord):
        if self.use_mongo:
            self.db.chat_messages.update_one(
                {"_id": msg.id},
                {"$set": msg.model_dump(by_alias=True)},
                upsert=True,
            )
        else:
            self.mem_messages[msg.id] = msg

    def get_chat_history(self, project_id: str = "global") -> List[ChatMessageRecord]:
        if self.use_mongo:
            docs = list(
                self.db.chat_messages.find({"project_id": project_id}).sort(
                    "created_at", 1
                )
            )
            return [ChatMessageRecord(**d) for d in docs]
        else:
            msgs = [m for m in self.mem_messages.values() if m.project_id == project_id]
            return sorted(msgs, key=lambda m: m.created_at)


# Global Database Singleton
db_engine = GraphMemexDatabase()
