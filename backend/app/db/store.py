"""Mongo persistence for v2 tools (deterministic only)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from pymongo import MongoClient

from app.config import settings
from app.errors import ImmutableNodeViolation, NotFoundError
from app.models import (
    NodeKind,
    PendingApproval,
    StagingBundle,
    V2Edge,
    V2Node,
    V2Project,
    new_id,
)

GENESIS_TITLE = "Genesis"
MUTABLE_KINDS = {NodeKind.CONCEPT_M, NodeKind.INSIGHT, NodeKind.NOTE, NodeKind.TODO}


@dataclass
class ToolContext:
    project_id: str
    thread_id: str = "default"
    store: "V2Store" = None  # type: ignore[assignment]


class V2Store:
    def __init__(self, db_name: Optional[str] = None):
        self._client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=2000)
        self._db = self._client[db_name or settings.DB_NAME]

    def close(self) -> None:
        self._client.close()

    # --- projects ---

    def create_project(self, name: str, project_id: Optional[str] = None) -> V2Project:
        pid = project_id or new_id("proj")
        genesis_id = f"genesis_{pid}"
        project = V2Project(
            _id=pid,
            name=name,
            introduction="",
            genesis_node_id=genesis_id,
        )
        genesis = V2Node(
            _id=genesis_id,
            title=GENESIS_TITLE,
            description="Project spine",
            node_kind=NodeKind.CONCEPT_M,
            project_id=pid,
            metadata={"genesis": True},
        )
        self._db.projects.insert_one(project.to_mongo())
        self._db.nodes.insert_one(genesis.to_mongo())
        self._db.projects.update_one(
            {"_id": pid},
            {"$push": {"node_ids": genesis_id}},
        )
        return project

    def get_project(self, project_id: str) -> V2Project:
        doc = self._db.projects.find_one({"_id": project_id})
        if not doc:
            raise NotFoundError(project_id)
        return V2Project(
            _id=doc["_id"],
            name=doc["name"],
            introduction=doc.get("introduction") or doc.get("description", ""),
            genesis_node_id=doc.get("genesis_node_id", f"genesis_{project_id}"),
            created_at=doc.get("created_at", time.time()),
        )

    def update_project_scope(self, project_id: str, introduction: str) -> None:
        self._db.projects.update_one(
            {"_id": project_id},
            {"$set": {"introduction": introduction, "description": introduction}},
        )
        proj = self.get_project(project_id)
        self._db.nodes.update_one(
            {"_id": proj.genesis_node_id},
            {"$set": {"description": introduction, "updated_at": time.time()}},
        )

    # --- nodes ---

    def get_node(self, node_id: str) -> V2Node:
        doc = self._db.nodes.find_one({"_id": node_id})
        if not doc:
            raise NotFoundError(node_id)
        return V2Node.from_mongo(doc)

    def upsert_node(self, node: V2Node) -> None:
        doc = node.to_mongo()
        doc["project_ids"] = [node.project_id]
        self._db.nodes.replace_one({"_id": node.id}, doc, upsert=True)

    def delete_node(self, node_id: str, *, force: bool = False) -> None:
        node = self.get_node(node_id)
        if not force and self._is_immutable(node):
            raise ImmutableNodeViolation(f"Cannot delete {node_id}")
        self._db.nodes.delete_one({"_id": node_id})
        self._db.edges.delete_many(
            {"$or": [{"source_id": node_id}, {"target_id": node_id}]}
        )

    def list_nodes(
        self, project_id: str, kinds: Optional[list[NodeKind]] = None
    ) -> list[V2Node]:
        query: dict[str, Any] = {"project_ids": project_id}
        docs = self._db.nodes.find(query)
        nodes = [V2Node.from_mongo(d) for d in docs]
        if kinds:
            nodes = [n for n in nodes if n.node_kind in kinds]
        return nodes

    def _is_immutable(self, node: V2Node) -> bool:
        if node.node_kind == NodeKind.ROOT:
            return True
        if node.node_kind == NodeKind.CONCEPT_I:
            return True
        return bool(node.metadata.get("immutable"))

    def assert_mutable(self, node_id: str) -> V2Node:
        node = self.get_node(node_id)
        if self._is_immutable(node):
            raise ImmutableNodeViolation(node_id)
        return node

    # --- edges ---

    def add_edge(self, edge: V2Edge) -> None:
        self._db.edges.replace_one({"_id": edge.id}, edge.to_mongo(), upsert=True)

    def remove_edge(self, edge_id: str) -> None:
        self._db.edges.delete_one({"_id": edge_id})

    def find_edge(self, source_id: str, target_id: str) -> Optional[V2Edge]:
        doc = self._db.edges.find_one(
            {
                "$or": [
                    {"source_id": source_id, "target_id": target_id},
                    {"source_id": target_id, "target_id": source_id},
                ]
            }
        )
        if not doc:
            return None
        return V2Edge(
            _id=doc["_id"],
            source_id=doc["source_id"],
            target_id=doc["target_id"],
            note=doc.get("note") or doc.get("description", ""),
            project_id=(doc.get("project_ids") or ["global"])[0],
        )

    def neighbors(self, node_id: str) -> list[str]:
        ids: set[str] = set()
        for doc in self._db.edges.find(
            {"$or": [{"source_id": node_id}, {"target_id": node_id}]}
        ):
            other = (
                doc["target_id"] if doc["source_id"] == node_id else doc["source_id"]
            )
            ids.add(other)
        return list(ids)

    def degree(self, node_id: str) -> int:
        return len(self.neighbors(node_id))

    # --- passages ---

    def upsert_passage(
        self, passage_id: str, doc_id: str, text: str, index: int = 0
    ) -> None:
        self._db.passages.replace_one(
            {"_id": passage_id},
            {
                "_id": passage_id,
                "doc_id": doc_id,
                "chunk_index": index,
                "text_content": text,
                "created_at": time.time(),
            },
            upsert=True,
        )

    def get_passages(self, passage_ids: list[str]) -> list[dict[str, Any]]:
        return list(self._db.passages.find({"_id": {"$in": passage_ids}}))

    # --- staging ---

    def upsert_staging(self, key: str, bundle: StagingBundle) -> None:
        self._db.staging.replace_one(
            {"_id": key},
            {"_id": key, **bundle.model_dump()},
            upsert=True,
        )

    def get_staging(self, key: str) -> StagingBundle:
        doc = self._db.staging.find_one({"_id": key})
        if not doc:
            raise NotFoundError(key)
        doc.pop("_id", None)
        return StagingBundle(**doc)

    # --- dock ---

    def enqueue_approval(self, item: PendingApproval) -> str:
        self._db.pending_approvals.insert_one(item.model_dump(by_alias=True))
        return item.id

    def list_pending(
        self, project_id: str, thread_id: Optional[str] = None
    ) -> list[PendingApproval]:
        q: dict[str, Any] = {"project_id": project_id, "status": "pending"}
        if thread_id:
            q["thread_id"] = thread_id
        return [
            PendingApproval(**d)
            for d in self._db.pending_approvals.find(q).sort("created_at", 1)
        ]

    def resolve_approval(self, approval_id: str, action: str) -> PendingApproval:
        doc = self._db.pending_approvals.find_one({"_id": approval_id})
        if not doc:
            raise NotFoundError(approval_id)
        status = "approved" if action == "approve" else "dismissed"
        self._db.pending_approvals.update_one(
            {"_id": approval_id}, {"$set": {"status": status}}
        )
        doc["status"] = status
        return PendingApproval(**doc)

    # --- highlights (session) ---

    def set_highlight_ids(self, thread_id: str, node_ids: list[str]) -> None:
        self._db.highlights.replace_one(
            {"_id": thread_id},
            {"_id": thread_id, "node_ids": node_ids},
            upsert=True,
        )

    def get_highlight_ids(self, thread_id: str) -> list[str]:
        doc = self._db.highlights.find_one({"_id": thread_id})
        return doc.get("node_ids", []) if doc else []


_store: Optional[V2Store] = None


def get_store(db_name: Optional[str] = None) -> V2Store:
    global _store
    if db_name is not None:
        return V2Store(db_name=db_name)
    if _store is None:
        _store = V2Store()
    return _store
