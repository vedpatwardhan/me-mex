"""
Universal Storage & Domain Models: Me-Mex

Aligned with docs/ARCHITECTURE.md Section 3:
- Universal Graph Network: Root Nodes (Document Summaries), Concept Nodes (Immutable vs. Mutable), and Typed Relation Edges.
- First-Class Temporal Reasoning: Explicit creation/update timestamps (`created_at`, `updated_at`) on all nodes/edges without artificial numerical weight decay.
- Node Mutability Hierarchy:
    - Root Nodes (`ROOT`) & Intra-Document Concept Nodes (direct extracted concepts connected to Root Nodes) are Immutable (`metadata.immutable = True`).
    - Persona-created Domain Hubs & Intermediate Nodes are Mutable (`metadata.immutable = False`).
"""

import time
from typing import Dict, List, Literal, Optional, Any
from pydantic import BaseModel, Field

# Canonical Node Types
ROOT_NODE_TYPES = {"paper", "blog", "video", "post", "ROOT"}
NodeType = Literal["paper", "blog", "video", "post", "concept", "ROOT", "CONCEPT"]


class GraphNode(BaseModel):
    """
    Universal Active Graph Network Node Entity.

    Stores node metadata, title, description, and passage chunk references.
    Note: Raw passage text chunks are stored out-of-graph in the `passages` collection
    and referenced via `passage_ids` to keep the active graph topology clean.
    """

    id: str = Field(alias="_id")
    node_type: NodeType = "concept"
    title: str
    description: str = ""
    passage_ids: List[str] = Field(
        default_factory=list
    )  # Out-of-graph passage chunk ID pointers
    project_ids: List[str] = Field(default_factory=lambda: ["global"])
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def is_root_node(self) -> bool:
        """Returns True if node represents a base document container (paper, blog, video, post)."""
        return self.node_type in ROOT_NODE_TYPES

    @property
    def is_immutable(self) -> bool:
        """
        Returns True if node represents ground-truth evidence (Root Node or Intra-Document Concept)
        that cannot be modified, split, or deleted by persona agents.
        """
        if self.is_root_node or self.metadata.get("immutable", False):
            return True
        return False

    def to_prompt_dict(self) -> Dict[str, str]:
        """Returns clean representation (id, title, description) for LLM prompts."""
        return {"id": self.id, "title": self.title, "description": self.description}


class ConceptHubCandidate(BaseModel):
    """
    Candidate Concept Hub Entity identified via graph centrality analytics.
    Exposes explicit schema guarantees for ID, Title, Description, and centrality score.
    Supports unpacking or tuple indexing for backward compatibility.
    """

    node: GraphNode
    centrality_score: float

    @property
    def id(self) -> str:
        return self.node.id

    @property
    def title(self) -> str:
        return self.node.title

    @property
    def description(self) -> str:
        return self.node.description

    def __getitem__(self, item: int):
        """Enable tuple unpacking / indexing (candidate[0] -> node, candidate[1] -> score)."""
        if item == 0:
            return self.node
        elif item == 1:
            return self.centrality_score
        raise IndexError(
            "ConceptHubCandidate only supports indices 0 (node) and 1 (score)"
        )

    def __iter__(self):
        """Enable unpacking: node, score = candidate."""
        return iter((self.node, self.centrality_score))


class GraphEdge(BaseModel):
    """
    Qualitative Typed Relation Edge Entity.

    Represents unweighted qualitative relationships (`SUBSET_OF`, `SUPERSET_OF`, `RELEVANT_TO`,
    `BUILDS_UPON`, `SUPERSEDES`, `PARALLEL_TO`, `CONTRASTS_WITH`) contextualized with descriptions.
    Temporal progression is tracked directly via `created_at` timestamps without artificial numerical weight decay.
    """

    id: str = Field(alias="_id")
    source_id: str
    target_id: str
    is_directional: bool = True  # False for symmetric parallel concepts
    description: str = ""  # Natural language explanation of relationship
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
    created_at: float = Field(default_factory=time.time)


# 5. Department Macro Document Record
class MacroDocumentRecord(BaseModel):
    id: str = Field(alias="_id")
    department_name: str
    hub_concept_ids: List[str] = Field(default_factory=list)
    summary_text: str
    last_updated: float = Field(default_factory=time.time)

    @property
    def department_id(self) -> str:
        return self.id


# 6. Staging Sandbox Record
class StagingRecord(BaseModel):
    id: str = Field(alias="_id")
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


# 8. Project-Scoped Chat Message Record
class ChatMessageRecord(BaseModel):
    id: str = Field(alias="_id")
    project_id: str = "global"
    sender: Literal["user", "agent"]
    text: str
    is_voice: bool = False
    grounded_node_ids: List[str] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)


# 9. Project-Scoped System Event Record (Last 15 Queue)
class ProjectEventRecord(BaseModel):
    id: str = Field(alias="_id")
    project_id: str = "global"
    event_type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)


# 10. Persona Ingestion Command Models
class ConceptCommandData(BaseModel):
    id: Optional[str] = Field(
        default=None,
        description="ID of existing graph node for EDIT/DELETE or candidate ID for CREATE/EDIT.",
    )
    title: str = Field(..., description="Title of the concept.")
    description: str = Field(
        default="", description="Description or insight body of the concept."
    )
    passage_ids: List[str] = Field(
        default_factory=list, description="Associated passage IDs."
    )


class EdgeCommandData(BaseModel):
    id: Optional[str] = Field(
        default=None, description="ID of existing edge for EDIT_EDGE or DELETE_EDGE."
    )
    source_id: Optional[str] = Field(
        default=None,
        description="Candidate node ID or existing node ID for source concept.",
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Candidate node ID or existing node ID for target concept.",
    )
    description: str = Field(
        default="", description="Qualitative relationship description."
    )


class PersonaIngestionCommand(BaseModel):
    command_type: Literal[
        "CREATE_CONCEPT",
        "EDIT_CONCEPT",
        "DELETE_CONCEPT",
        "CONSTRUCT_EDGE",
        "EDIT_EDGE",
        "DELETE_EDGE",
    ]
    concept: Optional[ConceptCommandData] = None
    edge: Optional[EdgeCommandData] = None


# 11. Canonical Structured Output Models for Backend LLM Calls


class IntentClassificationPayload(BaseModel):
    intent: Literal["CONVERSATION", "RETRIEVAL", "INGESTION"]
    doc_type: Optional[str] = None
    source_url: Optional[str] = None
    raw_text: Optional[str] = None


class ConceptExtractionItem(BaseModel):
    idx: int
    title: str
    description: str


class PassageConceptsPayload(BaseModel):
    concepts: List[ConceptExtractionItem]


class CanonicalConceptItem(BaseModel):
    title: str
    description: str
    passage_indices: List[int] = Field(default_factory=list)


class ConsolidatedConceptsPayload(BaseModel):
    doc_description: str
    doc_type: Optional[str] = None
    concepts: List[CanonicalConceptItem]


class ExploredDomainContext(BaseModel):
    """Typed context for an explored department persona domain."""

    department_id: str
    department_name: str
    hub_node: GraphNode
    explored_nodes: List[GraphNode] = Field(default_factory=list)


class EdgeCommandPayload(BaseModel):
    source_index: int
    target_index: int
    relation_type: str = "RELEVANT_TO"
    description: str = ""
    domain_hub_index: Optional[int] = None


class ConceptEditPayload(BaseModel):
    concept_index: int
    title: Optional[str] = None
    description: Optional[str] = None


class LinkingCommand(BaseModel):
    action: Literal["CREATE_EDGE", "EDIT_CONCEPT"] = "CREATE_EDGE"
    edge: Optional[EdgeCommandPayload] = None
    concept: Optional[ConceptEditPayload] = None
    department_name: Optional[str] = None
    persona_id: Optional[str] = None


class CollectiveLinkingPayload(BaseModel):
    commands: List[LinkingCommand]


class PersonaRouteRelevancePayload(BaseModel):
    selected_hub_indices: List[int]
    reasoning: Optional[str] = None


class DiscoveredCandidateItem(BaseModel):
    candidate_index: int
    rationale: str = ""


class ReorgDiscoveryPayload(BaseModel):
    candidates: List[DiscoveredCandidateItem] = Field(default_factory=list)


class SubConceptItem(BaseModel):
    sub_id_alias: str
    title: str
    description: str


class ReorgSplitPayload(BaseModel):
    sub_concepts: List[SubConceptItem]


class RewireEdgeItem(BaseModel):
    neighbor_index: int
    connect_to_sub_alias: str
    relation_type: str = "SUBSET_OF"
    description: str = ""


class ReorgRewirePayload(BaseModel):
    rewired_edges: List[RewireEdgeItem]


class PersonaIngestionCommandsPayload(BaseModel):
    commands: List[PersonaIngestionCommand]


class SelectedNeighborItem(BaseModel):
    neighbor_index: int
    rationale: str = ""


class PersonaExplorationPayload(BaseModel):
    synthesized_insight: Optional[str] = None
    selected_neighbors: List[SelectedNeighborItem] = Field(default_factory=list)
