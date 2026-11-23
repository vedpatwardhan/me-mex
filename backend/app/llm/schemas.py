"""Pydantic outputs for LangChain structured steps."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkerName = Literal[
    "conversation",
    "gist",
    "intradoc",
    "link",
    "reorg",
    "retrieval",
    "scratch",
    "project_scope",
    "job_control",
]
WorkerIntent = Literal[
    "conversation",
    "source_summary",
    "source_analysis",
    "commit_gist",
    "create_note",
    "create_todo",
    "promote_todo",
    "scope_conversation",
    "scope_save",
    "link",
    "reorg",
    "retrieval",
    "status",
    "job_control",
]
ScopeRevisionMode = Literal["incremental", "replace"]
JobAction = Literal["pause", "resume", "cancel", "delete"]


class WorkerRoute(BaseModel):
    worker: WorkerName
    intent: WorkerIntent
    dispatch: bool
    reply: str | None = None
    source_field: str | None = None
    source_reference: str | None = None
    source_error: str | None = None
    title: str | None = None
    content: str | None = None
    target_id: str | None = None
    job_action: JobAction | None = None
    root_id: str | None = None
    target_ids: list[str] | None = None


class ProjectScopeResult(BaseModel):
    revision_mode: ScopeRevisionMode
    proposed_introduction: str


class PassageConcept(BaseModel):
    idx: int
    title: str
    description: str


class PassageExtractResult(BaseModel):
    concepts: list[PassageConcept] = Field(default_factory=list)


class CanonicalConcept(BaseModel):
    title: str
    description: str
    passage_indices: list[int] = Field(default_factory=list)


class ConsolidateResult(BaseModel):
    doc_description: str = ""
    doc_type: str = "paper"
    concepts: list[CanonicalConcept] = Field(default_factory=list)
