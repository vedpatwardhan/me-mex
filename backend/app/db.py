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
)

# Try PyMongo import, fall back gracefully if MongoDB server is offline/not installed
try:
    import pymongo
    from pymongo import MongoClient

    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

# MongoDB Connection Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "me-mex")


class GraphMemexDatabase:
    """Hybrid MongoDB Database Engine with in-memory fallback for local execution."""

    def __init__(self):
        self.use_mongo = False
        self.client = None
        self.db = None

        # In-memory fallbacks
        self.mem_documents: Dict[str, DocumentRecord] = {}
        self.mem_passages: Dict[str, PassageRecord] = {}
        self.mem_nodes: Dict[str, GraphNode] = {}
        self.mem_edges: Dict[str, GraphEdge] = {}
        self.mem_staging: Dict[str, StagingRecord] = {}
        self.mem_projects: Dict[str, ProjectWorkspace] = {}

        if HAS_PYMONGO:
            try:
                self.client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
                self.client.admin.command("ping")
                self.db = self.client[DB_NAME]
                self.use_mongo = True
                print(f"[Database] Connected to MongoDB at {MONGO_URI}, DB: {DB_NAME}")
            except Exception as e:
                print(
                    f"[Database] MongoDB unavailable ({e}). Running in-memory fallback mode."
                )
                self.use_mongo = False
        else:
            print("[Database] PyMongo not installed. Running in-memory fallback mode.")

        self._seed_initial_data()

    def _seed_initial_data(self):
        """Seed initial nodes, edges, and default projects if empty."""
        if not self.get_projects():
            global_proj = ProjectWorkspace(
                _id="global",
                name="Global Master Graph",
                description="Master superset database across all paradigms and literature.",
            )
            self.upsert_project(global_proj)
        if not self.get_nodes():
            n1 = GraphNode(
                _id="concept_world_models",
                title="World Models",
                text_body="# World Models\nGeneral paradigm of generative world models in robotics.",
                metadata={"domain_tags": ["world_models"]},
            )
            n2 = GraphNode(
                _id="concept_pixel_world_models",
                title="Pixel-Space World Models",
                text_body="# Pixel-Space World Models\nGenerates future raw RGB frames directly (e.g. World Models 2018).",
                metadata={
                    "domain_tags": ["pixel_space"],
                    "status": "HISTORICAL_SUPERSEDED",
                },
                passage_pointers=["pass_pixel_01"],
            )
            n3 = GraphNode(
                _id="concept_latent_world_models",
                title="Latent-Space World Models",
                text_body="# Latent-Space World Models\nGenerates representations in latent space for 100x faster planning (e.g. LeWM, JEPA).",
                metadata={"domain_tags": ["latent_space"], "status": "PRIMARY_ACTIVE"},
                passage_pointers=["pass_latent_01"],
            )
            n4 = GraphNode(
                _id="concept_action_mpc",
                title="Action Planning via MPC",
                text_body="# Action Planning via MPC\nTrajectory optimization over world model rollouts.",
                metadata={"domain_tags": ["planning", "mpc"]},
            )

            for n in [n1, n2, n3, n4]:
                self.upsert_node(n)

            e1 = GraphEdge(
                _id="edge_pixel_to_mpc",
                source_id="concept_pixel_world_models",
                target_id="concept_action_mpc",
                is_directional=True,
                text_body="Historical MPC rollout over raw pixel predictions.",
                weight=0.3,
                status="HISTORICAL_SUPERSEDED",
            )
            e2 = GraphEdge(
                _id="edge_latent_to_mpc",
                source_id="concept_latent_world_models",
                target_id="concept_action_mpc",
                is_directional=True,
                text_body="Primary SOTA 100x speedup for MPC action planning in latent space.",
                weight=1.0,
                status="PRIMARY_ACTIVE",
            )
            e3 = GraphEdge(
                _id="edge_pixel_parallel_latent",
                source_id="concept_pixel_world_models",
                target_id="concept_latent_world_models",
                is_directional=False,
                text_body="Parallel generative world model paradigms operating on raw pixels vs latent embeddings.",
                weight=1.0,
                status="PRIMARY_ACTIVE",
            )
            for e in [e1, e2, e3]:
                self.upsert_edge(e)

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


# Global Database Singleton
db_engine = GraphMemexDatabase()
