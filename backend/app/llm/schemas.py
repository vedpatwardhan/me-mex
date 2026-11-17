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
]


class WorkerRoute(BaseModel):
    worker: WorkerName


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
