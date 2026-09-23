from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

NodeType = Literal[
    "paper",  # Blue: Academic research papers & preprints
    "blog",  # Green: Technical blog posts & web articles
    "video",  # Red: YouTube video transcripts & lectures
    "post",  # Purple: Social posts, tweets, forum updates, short notes
    "concept",  # Yellow: Atomic self-evolving Zettelkasten concept nodes
]


class GraphNode(BaseModel):
    id: str
    node_type: NodeType
    title: str
    takeaway_2line: str
    content: str = ""
    raw_doc_id: Optional[str] = None
    project_ids: List[str] = Field(default_factory=lambda: ["global"])
    metadata: Dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class GraphEdge(BaseModel):
    id: str
    source_node_id: str
    target_node_id: str
    is_directional: bool = True  # False for symmetric parallel concepts
    text_body: str = ""  # Natural language explanation of relationship
    weight: float = 1.0
    provenance_quote: Optional[str] = None
    project_ids: List[str] = Field(default_factory=lambda: ["global"])
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class RawDocument(BaseModel):
    id: str
    source_type: Literal[
        "pdf", "web_snapshot", "tweet", "video_transcript", "voice_epiphany"
    ]
    title: str
    raw_content: str
    original_url: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    temporal_timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )


class ProjectWorkspace(BaseModel):
    id: str
    name: str
    description: str
    node_ids: List[str] = Field(default_factory=list)
    edge_ids: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentProposal(BaseModel):
    id: str
    proposal_type: Literal["link", "node", "hypothesis", "merge"]
    title: str
    description: str
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    suggested_edge_type: Optional[EdgeType] = None
    status: Literal["pending", "accepted", "rejected"] = "pending"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ReportRequest(BaseModel):
    title: str
    target_node_ids: List[str]
    project_id: Optional[str] = "global"


class ReportResponse(BaseModel):
    id: str
    title: str
    markdown_content: str
    provenance_mappings: Dict[str, str]  # phrase/section -> node_id mapping
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class IntakeRequest(BaseModel):
    source_type: Literal["pdf", "url", "voice", "text"]
    content_or_url: str
    title_hint: Optional[str] = None
    project_id: Optional[str] = "global"
