"""Domain models aligned with me-mex/docs/03-graph-and-memory.md."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeKind(str, Enum):
    ROOT = "ROOT"
    CONCEPT_I = "CONCEPT_I"
    CONCEPT_M = "CONCEPT_M"
    INSIGHT = "INSIGHT"
    NOTE = "NOTE"
    TODO = "TODO"


class TodoStatus(str, Enum):
    open = "open"
    done = "done"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Node(BaseModel):
    id: str = Field(alias="_id")
    title: str
    description: str = ""
    node_kind: NodeKind
    project_id: str
    source_uri: str | None = None
    passage_ids: list[str] = Field(default_factory=list)
    parent_root_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def to_mongo(self) -> dict[str, Any]:
        doc = self.model_dump(by_alias=True)
        doc["metadata"] = {**doc.get("metadata", {}), "node_kind": self.node_kind.value}
        doc["node_type"] = "ROOT" if self.node_kind == NodeKind.ROOT else "concept"
        if self.node_kind == NodeKind.CONCEPT_I:
            doc["metadata"]["immutable"] = True
        return doc

    @classmethod
    def from_mongo(cls, doc: dict[str, Any]) -> Node:
        kind = doc.get("metadata", {}).get("node_kind") or "CONCEPT_M"
        return cls(
            _id=doc["_id"],
            title=doc.get("title", ""),
            description=doc.get("description", ""),
            node_kind=NodeKind(kind),
            project_id=(doc.get("project_ids") or [doc.get("project_id", "")])[0]
            if doc.get("project_ids")
            else doc.get("project_id", "global"),
            source_uri=doc.get("metadata", {}).get("source_uri"),
            passage_ids=doc.get("passage_ids") or [],
            parent_root_id=doc.get("metadata", {}).get("parent_root_id"),
            metadata=doc.get("metadata") or {},
            created_at=doc.get("created_at", time.time()),
            updated_at=doc.get("updated_at", time.time()),
        )


class Edge(BaseModel):
    id: str = Field(alias="_id")
    source_id: str
    target_id: str
    note: str = ""
    project_id: str
    created_at: float = Field(default_factory=time.time)

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "description": self.note,
            "note": self.note,
            "project_ids": [self.project_id],
            "metadata": {},
            "created_at": self.created_at,
        }


class Project(BaseModel):
    id: str = Field(alias="_id")
    name: str
    introduction: str = ""
    genesis_node_id: str = ""
    created_at: float = Field(default_factory=time.time)

    def to_mongo(self) -> dict[str, Any]:
        return {
            "_id": self.id,
            "name": self.name,
            "description": self.introduction,
            "introduction": self.introduction,
            "genesis_node_id": self.genesis_node_id,
            "created_at": self.created_at,
            "node_ids": [],
            "edge_ids": [],
        }


class StagingConcept(BaseModel):
    concept_id: str
    title: str
    description: str = ""
    passage_indices: list[int] = Field(default_factory=list)
    dropped: bool = False


class StagingPassage(BaseModel):
    passage_index: int
    text: str


class StagingBundle(BaseModel):
    root_id: str | None = None
    pending_url: str | None = None
    source_title: str = ""
    doc_description: str = ""
    doc_type: str = "paper"
    content_hash: str = ""
    concepts: list[StagingConcept] = Field(default_factory=list)
    passages: list[StagingPassage] = Field(default_factory=list)
    updated_at: float = Field(default_factory=time.time)


class PendingApproval(BaseModel):
    id: str = Field(alias="_id")
    project_id: str
    thread_id: str
    approval_type: str
    title: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "approved", "dismissed"] = "pending"
    created_at: float = Field(default_factory=time.time)


class AgentTurnRequest(BaseModel):
    """Agent turn envelope; use ``context_json.dock_turn`` for plane-1 voice (see ``/api/conversation/turn/stream``)."""

    text: str
    thread_id: str
    context_json: dict[str, Any] = Field(default_factory=dict)


class AgentResumeRequest(BaseModel):
    thread_id: str
    approval_id: str
    action: Literal["approve", "dismiss"]
    context_json: dict[str, Any] = Field(default_factory=dict)


class TurnAbortRequest(BaseModel):
    thread_id: str
    turn_id: str


class TurnRevertRequest(BaseModel):
    thread_id: str
    turn_id: str
    project_id: str
