import os
import time
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# Try PyMongo import, fall back gracefully if MongoDB server is offline/not installed
try:
    import pymongo
    from pymongo import MongoClient

    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

# MongoDB Connection Configuration
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "graph_memex_db")


class DocumentRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    title: str
    file_path: str
    media_type: str = "PAPER"  # "PAPER" | "BLOG" | "TRANSCRIPT" | "CODE"
    source_url: Optional[str] = None
    ingested_at: float = Field(default_factory=time.time)


class PassageRecord(BaseModel):
    id: str = Field(alias="_id")
    doc_id: str
    chunk_index: int
    text_content: str
    embedding_vector: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)


class GraphNodeRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    node_class: str = "CONCEPT"  # "ROOT_MEDIA" | "CONCEPT"
    title: str
    text_body: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding_vector: Optional[List[float]] = None
    passage_pointers: List[str] = Field(default_factory=list)  # Passage IDs
    updated_at: float = Field(default_factory=time.time)


class ConnectionEdgeRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    source_id: str
    target_id: str
    is_directional: bool = True  # Set to False for symmetric parallel concepts
    text_body: str  # Natural language explanation of relationship
    weight: float = 1.0  # Decays to 0.3 when superseded
    status: str = "PRIMARY_ACTIVE"  # "PRIMARY_ACTIVE" | "HISTORICAL_SUPERSEDED"
    created_at: float = Field(default_factory=time.time)


class MacroDocumentRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    department_name: str
    hub_concept_ids: List[str] = Field(default_factory=list)
    summary_text: str
    last_updated: float = Field(default_factory=time.time)


class StagingRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    title: str
    raw_content: str
    source_type: str = "url"
    status: str = "STAGED"  # "STAGED" | "INTEGRATED" | "REJECTED"
    extracted_candidate_concepts: List[str] = Field(default_factory=list)


class GraphMemexDatabase:
    """Hybrid MongoDB Database Engine with in-memory fallback for local execution."""

    def __init__(self):
        self.use_mongo = False
        self.client = None
        self.db = None

        # In-memory fallbacks
        self.mem_documents: Dict[str, DocumentRecord] = {}
        self.mem_passages: Dict[str, PassageRecord] = {}
        self.mem_nodes: Dict[str, GraphNodeRecord] = {}
        self.mem_edges: Dict[str, ConnectionEdgeRecord] = {}
        self.mem_macro: Dict[str, MacroDocumentRecord] = {}
        self.mem_staging: Dict[str, StagingRecord] = {}

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
        """Seed initial nodes, edges, and macro documents if empty."""
        if not self.get_nodes():
            n1 = GraphNodeRecord(
                _id="concept_world_models",
                title="World Models",
                text_body="# World Models\nGeneral paradigm of generative world models in robotics.",
                metadata={"domain_tags": ["world_models"]},
            )
            n2 = GraphNodeRecord(
                _id="concept_pixel_world_models",
                title="Pixel-Space World Models",
                text_body="# Pixel-Space World Models\nGenerates future raw RGB frames directly (e.g. World Models 2018).",
                metadata={
                    "domain_tags": ["pixel_space"],
                    "status": "HISTORICAL_SUPERSEDED",
                },
                passage_pointers=["pass_pixel_01"],
            )
            n3 = GraphNodeRecord(
                _id="concept_latent_world_models",
                title="Latent-Space World Models",
                text_body="# Latent-Space World Models\nGenerates representations in latent space for 100x faster planning (e.g. LeWM, JEPA).",
                metadata={"domain_tags": ["latent_space"], "status": "PRIMARY_ACTIVE"},
                passage_pointers=["pass_latent_01"],
            )
            n4 = GraphNodeRecord(
                _id="concept_action_mpc",
                title="Action Planning via MPC",
                text_body="# Action Planning via MPC\nTrajectory optimization over world model rollouts.",
                metadata={"domain_tags": ["planning", "mpc"]},
            )

            for n in [n1, n2, n3, n4]:
                self.upsert_node(n)

            e1 = ConnectionEdgeRecord(
                _id="edge_pixel_to_mpc",
                source_id="concept_pixel_world_models",
                target_id="concept_action_mpc",
                is_directional=True,
                text_body="Historical MPC rollout over raw pixel predictions.",
                weight=0.3,
                status="HISTORICAL_SUPERSEDED",
            )
            e2 = ConnectionEdgeRecord(
                _id="edge_latent_to_mpc",
                source_id="concept_latent_world_models",
                target_id="concept_action_mpc",
                is_directional=True,
                text_body="Primary SOTA 100x speedup for MPC action planning in latent space.",
                weight=1.0,
                status="PRIMARY_ACTIVE",
            )
            e3 = ConnectionEdgeRecord(
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

            macro1 = MacroDocumentRecord(
                _id="macro_dept_world_models",
                department_name="World Models & Latent Dynamics",
                hub_concept_ids=["concept_world_models", "concept_latent_world_models"],
                summary_text="# Macro Department: World Models\nSummary of transition from pixel-space to latent-space world models.",
            )
            self.upsert_macro(macro1)

    # --- Node Operations ---
    def upsert_node(self, node: GraphNodeRecord):
        if self.use_mongo:
            self.db.nodes.update_one(
                {"_id": node.id}, {"$set": node.model_dump(by_alias=True)}, upsert=True
            )
        else:
            self.mem_nodes[node.id] = node

    def get_nodes(self, theme_id: Optional[str] = None) -> List[GraphNodeRecord]:
        if self.use_mongo:
            query = {"theme_id": theme_id} if theme_id and theme_id != "global" else {}
            docs = list(self.db.nodes.find(query))
            return [GraphNodeRecord(**d) for d in docs]
        else:
            return list(self.mem_nodes.values())

    def get_node(self, node_id: str) -> Optional[GraphNodeRecord]:
        if self.use_mongo:
            doc = self.db.nodes.find_one({"_id": node_id})
            return GraphNodeRecord(**doc) if doc else None
        else:
            return self.mem_nodes.get(node_id)

    # --- Edge Operations ---
    def upsert_edge(self, edge: ConnectionEdgeRecord):
        if self.use_mongo:
            self.db.edges.update_one(
                {"_id": edge.id}, {"$set": edge.model_dump(by_alias=True)}, upsert=True
            )
        else:
            self.mem_edges[edge.id] = edge

    def get_edges(self, theme_id: Optional[str] = None) -> List[ConnectionEdgeRecord]:
        if self.use_mongo:
            query = {"theme_id": theme_id} if theme_id and theme_id != "global" else {}
            docs = list(self.db.edges.find(query))
            return [ConnectionEdgeRecord(**d) for d in docs]
        else:
            return list(self.mem_edges.values())

    # --- Macro Documents ---
    def upsert_macro(self, macro: MacroDocumentRecord):
        if self.use_mongo:
            self.db.macro_documents.update_one(
                {"_id": macro.id},
                {"$set": macro.model_dump(by_alias=True)},
                upsert=True,
            )
        else:
            self.mem_macro[macro.id] = macro

    def get_macros(self) -> List[MacroDocumentRecord]:
        if self.use_mongo:
            docs = list(self.db.macro_documents.find())
            return [MacroDocumentRecord(**d) for d in docs]
        else:
            return list(self.mem_macro.values())

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
