"""Chat LLM client — live vLLM or deterministic stub for tests."""

from __future__ import annotations

import json
import re
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.config import settings
from app.models import Project
from app.prompts import load_prompt
from app.services.llm_tracer import llm_tracer

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


class ChatLLMProtocol(Protocol):
    def classify_worker(self, text: str, context: dict, project: Project) -> WorkerName:
        ...

    def conversation_reply(
        self,
        text: str,
        *,
        project: Project,
        gist_draft: str | None = None,
        scope_hint: str | None = None,
    ) -> str:
        ...

    def gist_draft(self, text: str, *, project: Project) -> str:
        ...

    def project_scope_reply(self, text: str, *, project: Project) -> str:
        ...

    def extract_passage(
        self,
        passage: str,
        *,
        doc_title: str,
        passage_index: int,
        user_intent: str,
    ) -> PassageExtractResult:
        ...

    def consolidate_extractions(
        self,
        raw_by_passage: list[PassageExtractResult],
        *,
        doc_title: str,
        user_intent: str,
    ) -> ConsolidateResult:
        ...

    def retrieval_summary(
        self, *, query: str, highlighted_ids: list[str], project: Project
    ) -> str:
        ...


def keyword_classify_worker(text: str, context: dict, project: Project) -> WorkerName:
    """Deterministic routing used by stub mode and as fallback."""
    t = text.lower()
    fields = context.get("custom_fields") or {}
    if "deep read" in t or "intra-doc" in t or "staging" in t:
        return "intradoc"
    if "where does" in t or "connect" in t or "place" in t:
        return "link"
    if "reorg" in t or "split" in t:
        return "reorg"
    if "what relates" in t or "retrieval" in t or "highlight" in t:
        return "retrieval"
    if "create note" in t or "create todo" in t or "promote todo" in t:
        return "scratch"
    if "create root" in t or "save gist" in t or fields.get("force_gist_commit"):
        return "gist"
    if "summarize" in t or ("gist" in t and "?" in t):
        return "conversation"
    if not (project.introduction or "").strip() and (
        "scope" in t or "introduction" in t or t.strip() in ("hello", "hi")
    ):
        return "project_scope"
    if "save scope" in t or "update_project_scope" in t:
        return "project_scope"
    return "conversation"


_DEFAULT_STUB_CONCEPTS = [
    {"concept_id": "c1", "title": "Main claim", "description": "Extracted concept."},
]


_chat_llm_override: ChatLLMProtocol | None = None


def set_chat_llm_override(llm: ChatLLMProtocol | None) -> None:
    global _chat_llm_override
    _chat_llm_override = llm


class StubChatLLM:
    """No network — returns scripted outputs; routing matches integration tests."""

    recorded_intradoc: list[dict[str, str]] | None = None

    def _trace(self, caller: str, messages: list[dict], response: str) -> None:
        llm_tracer.log_call(
            caller=caller,
            model="stub",
            messages=messages,
            duration_seconds=0.0,
            temperature=0.0,
            max_tokens=0,
            response_raw=response,
            status="SUCCESS",
        )

    def classify_worker(self, text: str, context: dict, project: Project) -> WorkerName:
        worker = keyword_classify_worker(text, context, project)
        self._trace(
            "Supervisor.classify_worker",
            [{"role": "user", "content": text}],
            json.dumps({"worker": worker}),
        )
        return worker

    def conversation_reply(
        self,
        text: str,
        *,
        project: Project,
        gist_draft: str | None = None,
        scope_hint: str | None = None,
    ) -> str:
        if gist_draft:
            return gist_draft
        if scope_hint:
            return scope_hint
        scope = (project.introduction or "").strip()
        prefix = f"[stub] Project scope: {scope[:120]}… " if scope else "[stub] "
        return f"{prefix}You said: {text[:400]}"

    def gist_draft(self, text: str, *, project: Project) -> str:
        return "Here's a gist draft in thread only."

    def project_scope_reply(self, text: str, *, project: Project) -> str:
        if "save scope" in text.lower() or "update_project_scope" in text:
            return "Scope saved."
        return "Tell me what / where / why for this project."

    def extract_passage(
        self,
        passage: str,
        *,
        doc_title: str,
        passage_index: int,
        user_intent: str,
    ) -> PassageExtractResult:
        if self.recorded_intradoc:
            row = next(
                (
                    r
                    for r in self.recorded_intradoc
                    if r.get("passage_index") == passage_index
                ),
                self.recorded_intradoc[0],
            )
            result = PassageExtractResult(
                concepts=[
                    PassageConcept(
                        idx=0,
                        title=row["title"],
                        description=row.get("description", ""),
                    )
                ]
            )
        else:
            snippet = re.sub(r"\s+", " ", passage.strip())[:80]
            title = snippet or f"Passage {passage_index + 1}"
            result = PassageExtractResult(
                concepts=[
                    PassageConcept(
                        idx=0,
                        title=title,
                        description=f"Stub extract from {doc_title}.",
                    )
                ]
            )
        self._trace(
            "IntraDocWorker.extract_passage",
            [{"role": "user", "content": passage[:200]}],
            result.model_dump_json(),
        )
        return result

    def consolidate_extractions(
        self,
        raw_by_passage: list[PassageExtractResult],
        *,
        doc_title: str,
        user_intent: str,
    ) -> ConsolidateResult:
        if self.recorded_intradoc:
            concepts = [
                CanonicalConcept(
                    title=r["title"],
                    description=r.get("description", ""),
                    passage_indices=[r.get("passage_index", 0)],
                )
                for r in self.recorded_intradoc
            ]
            out = ConsolidateResult(
                doc_description=f"Recorded fixture for {doc_title}.",
                doc_type="paper",
                concepts=concepts,
            )
        else:
            merged: list[CanonicalConcept] = []
            for pi, batch in enumerate(raw_by_passage):
                for c in batch.concepts:
                    merged.append(
                        CanonicalConcept(
                            title=c.title,
                            description=c.description,
                            passage_indices=[pi],
                        )
                    )
            if not merged:
                merged = [
                    CanonicalConcept(
                        title="Main claim",
                        description="Stub consolidated concept.",
                        passage_indices=[0],
                    )
                ]
            out = ConsolidateResult(
                doc_description=f"Stub summary for {doc_title}.",
                doc_type="paper",
                concepts=merged[:5],
            )
        self._trace(
            "IntraDocWorker.consolidate",
            [{"role": "user", "content": doc_title}],
            out.model_dump_json(),
        )
        return out

    def retrieval_summary(
        self, *, query: str, highlighted_ids: list[str], project: Project
    ) -> str:
        n = len(highlighted_ids)
        return f"[stub] Highlighted {n} related nodes for: {query[:120]}"


class LiveChatLLM:
    """Ministral via LLMGateway — used when CHAT_LLM_MODE=live."""

    def __init__(self) -> None:
        from app.services.llm_gateway import llm_gateway

        self._gw = llm_gateway

    def classify_worker(self, text: str, context: dict, project: Project) -> WorkerName:
        system = load_prompt(
            "worker_route",
            project_scope=(project.introduction or "").strip() or "(empty)",
        )
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {"text": text, "context": context},
                    ensure_ascii=False,
                ),
            },
        ]
        route = self._gw.generate_structured_completion(
            messages,
            WorkerRoute,
            temperature=0.0,
            max_tokens=256,
            caller="Supervisor.classify_worker",
        )
        return route.worker

    def conversation_reply(
        self,
        text: str,
        *,
        project: Project,
        gist_draft: str | None = None,
        scope_hint: str | None = None,
    ) -> str:
        if gist_draft:
            return gist_draft
        if scope_hint:
            return scope_hint
        system = load_prompt(
            "conversation",
            project_scope=(project.introduction or "").strip(),
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        return self._gw.generate_chat_completion(
            messages,
            temperature=0.2,
            max_tokens=settings.CHAT_COMPLETION_MAX_TOKENS,
            caller="Conversation.reply",
        )

    def gist_draft(self, text: str, *, project: Project) -> str:
        messages = [
            {
                "role": "system",
                "content": load_prompt(
                    "conversation", project_scope=project.introduction or ""
                ),
            },
            {
                "role": "user",
                "content": (
                    "Draft a short ROOT gist from the user's message. "
                    "Do not claim anything was saved to the graph.\n\n"
                    f"{text}"
                ),
            },
        ]
        return self._gw.generate_chat_completion(
            messages,
            max_tokens=512,
            caller="GistWorker.draft",
        )

    def project_scope_reply(self, text: str, *, project: Project) -> str:
        system = load_prompt("project_scope")
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "current_scope": project.introduction or "",
                        "user_message": text,
                    }
                ),
            },
        ]
        return self._gw.generate_chat_completion(
            messages,
            max_tokens=512,
            caller="ProjectScope.reply",
        )

    def extract_passage(
        self,
        passage: str,
        *,
        doc_title: str,
        passage_index: int,
        user_intent: str,
    ) -> PassageExtractResult:
        system = load_prompt("passage_concept_extraction", doc_title=doc_title)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "passage_index": passage_index,
                        "user_intent": user_intent,
                        "passage": passage,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        return self._gw.generate_structured_completion(
            messages,
            PassageExtractResult,
            max_tokens=settings.LLM_COMPLETION_MAX_TOKENS,
            caller="IntraDocWorker.extract_passage",
        )

    def consolidate_extractions(
        self,
        raw_by_passage: list[PassageExtractResult],
        *,
        doc_title: str,
        user_intent: str,
    ) -> ConsolidateResult:
        system = load_prompt("consolidate_concepts", doc_title=doc_title)
        payload = {
            "user_intent": user_intent,
            "raw_passages": [r.model_dump() for r in raw_by_passage],
        }
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        return self._gw.generate_structured_completion(
            messages,
            ConsolidateResult,
            max_tokens=settings.CONSOLIDATION_MAX_TOKENS,
            caller="IntraDocWorker.consolidate",
        )

    def retrieval_summary(
        self, *, query: str, highlighted_ids: list[str], project: Project
    ) -> str:
        system = load_prompt("conversation", project_scope=project.introduction or "")
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"User asked: {query}\n"
                    f"Related node ids: {', '.join(highlighted_ids[:8])}\n"
                    "Give a brief summary; no graph writes."
                ),
            },
        ]
        return self._gw.generate_chat_completion(
            messages,
            max_tokens=settings.CHAT_COMPLETION_MAX_TOKENS,
            caller="RetrievalWorker.summary",
        )


def get_chat_llm() -> ChatLLMProtocol:
    if _chat_llm_override is not None:
        return _chat_llm_override
    if settings.CHAT_LLM_MODE == "live":
        return LiveChatLLM()
    return StubChatLLM()


def stub_intradoc_concepts() -> list[dict[str, str]]:
    return [dict(c) for c in _DEFAULT_STUB_CONCEPTS]
