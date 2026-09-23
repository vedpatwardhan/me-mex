import time
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, Field

# Canonical Node Types (4 Root Media Types + 1 Concept Type)
NodeType = Literal["paper", "blog", "video", "post", "concept"]

# 1. Universal Graph Node Model
class GraphNode(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    node_class: str = "CONCEPT"  # "ROOT_MEDIA" | "CONCEPT"
    node_type: NodeType = "concept"
    title: str
    takeaway_2line: str = ""
    text_body: str = ""
    passage_pointers: List[str] = Field(
        default_factory=list
    )  # Out-of-graph passage chunk IDs
    project_ids: List[str] = Field(default_factory=lambda: ["global"])
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding_vector: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


# 2. Dual-Mode Connection Edge Model
class GraphEdge(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    source_id: str
    target_id: str
    is_directional: bool = True  # False for symmetric parallel concepts
    text_body: str = ""  # Natural language explanation of relationship
    weight: float = 1.0  # Decays to 0.3 when superseded
    status: str = "PRIMARY_ACTIVE"  # "PRIMARY_ACTIVE" | "HISTORICAL_SUPERSEDED"
    provenance_quote: Optional[str] = None
    project_ids: List[str] = Field(default_factory=lambda: ["global"])
    created_at: float = Field(default_factory=time.time)

    # Aliases for frontend compatibility
    @property
    def source_node_id(self) -> str:
        return self.source_id

    @property
    def target_node_id(self) -> str:
        return self.target_id


# 3. Document Metadata Record
class DocumentRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    title: str
    file_path: str
    media_type: str = "PAPER"  # "PAPER" | "BLOG" | "TRANSCRIPT" | "CODE"
    source_url: Optional[str] = None
    ingested_at: float = Field(default_factory=time.time)


# 4. Out-of-Graph Passage Chunk Record
class PassageRecord(BaseModel):
    id: str = Field(alias="_id")
    doc_id: str
    chunk_index: int
    text_content: str
    embedding_vector: Optional[List[float]] = None
    created_at: float = Field(default_factory=time.time)


# 5. Department Macro Document Record
class MacroDocumentRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    department_name: str
    hub_concept_ids: List[str] = Field(default_factory=list)
    summary_text: str
    last_updated: float = Field(default_factory=time.time)


# 6. Staging Sandbox Record
class StagingRecord(BaseModel):
    id: str = Field(alias="_id")
    theme_id: str = "vla_research"
    title: str
    raw_content: str
    source_type: str = "url"
    status: str = "STAGED"  # "STAGED" | "INTEGRATED" | "REJECTED"
    extracted_candidate_concepts: List[str] = Field(default_factory=list)


# 7. Workspace Project & Agent Interaction Models
class ProjectWorkspace(BaseModel):
    id: str = Field(alias="_id")
    name: str
    description: str
    node_ids: List[str] = Field(default_factory=list)
    edge_ids: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


class AgentProposal(BaseModel):
    id: str = Field(alias="_id")
    proposal_type: str  # "link" | "concept_merge" | "decay"
    title: str
    description: str
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    status: str = "pending"  # "pending" | "accepted" | "rejected"
    created_at: float = Field(default_factory=time.time)


class IntakeRequest(BaseModel):
    source_type: str  # "url" | "text" | "voice" | "pdf"
    content_or_url: str
    title_hint: Optional[str] = None
    project_id: str = "global"


class ReportRequest(BaseModel):
    title: str
    project_id: str = "global"
    target_node_ids: List[str] = Field(default_factory=list)


class ReportResponse(BaseModel):
    id: str = Field(alias="_id")
    title: str
    markdown_content: str
    provenance_mappings: Dict[str, str] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
