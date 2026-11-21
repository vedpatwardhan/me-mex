"""
All worker LLM work — LangChain Runnable `.invoke()` only.
Workers must not import llm_gateway or call chat helpers directly.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.llm.budget import passage_chunk_size_chars
from app.llm.runnables import chat_llm, structured_llm
from app.llm.schemas import (
    CanonicalConcept,
    ConsolidateResult,
    PassageConcept,
    PassageExtractResult,
    WorkerName,
    WorkerRoute,
)
from app.models import Project
from app.prompts import load_prompt

STUB_CONCEPTS = [
    {"concept_id": "c1", "title": "Main claim", "description": "Extracted concept."},
]

_recorded_intradoc: list[dict[str, str]] | None = None


def set_recorded_intradoc(rows: list[dict[str, str]] | None) -> None:
    global _recorded_intradoc
    _recorded_intradoc = rows


def keyword_route(text: str, context: dict, project: Project) -> WorkerName:
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


def _concepts_from_consolidated(
    consolidated: ConsolidateResult,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, c in enumerate(consolidated.concepts):
        out.append(
            {
                "concept_id": f"c{i + 1}_{uuid.uuid4().hex[:6]}",
                "title": c.title,
                "description": c.description,
            }
        )
    return out or [dict(c) for c in STUB_CONCEPTS]


# --- Live chains (prompt | LangChain Runnable → vLLM) ---


def _live_supervisor() -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                load_prompt(
                    "worker_route",
                    project_scope="{project_scope}",
                ),
            ),
            ("human", "{payload}"),
        ]
    )
    return prompt | structured_llm(WorkerRoute, caller="Supervisor.classify", max_tokens=256)


def _live_conversation() -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("conversation", project_scope="{project_scope}")),
            ("human", "{text}"),
        ]
    )
    return prompt | chat_llm(caller="Conversation", max_tokens=settings.CHAT_COMPLETION_MAX_TOKENS)


def _live_gist_draft() -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("conversation", project_scope="{project_scope}")),
            (
                "human",
                "Draft a short ROOT gist (not saved). User:\n{text}",
            ),
        ]
    )
    return prompt | chat_llm(caller="Gist.draft", max_tokens=512)


def _live_scope() -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("project_scope")),
            ("human", "{payload}"),
        ]
    )
    return prompt | chat_llm(caller="ProjectScope", max_tokens=512)


def _live_retrieval_summary() -> Runnable:
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("conversation", project_scope="{project_scope}")),
            ("human", "{payload}"),
        ]
    )
    return prompt | chat_llm(
        caller="Retrieval.summary", max_tokens=settings.CHAT_COMPLETION_MAX_TOKENS
    )


def _live_intradoc() -> Runnable:
    map_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                load_prompt("passage_concept_extraction", doc_title="{doc_title}"),
            ),
            ("human", "{chunk_payload}"),
        ]
    )
    map_chain = map_prompt | structured_llm(
        PassageExtractResult,
        caller="IntraDoc.map",
        max_tokens=settings.LLM_COMPLETION_MAX_TOKENS,
    )

    reduce_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", load_prompt("consolidate_concepts", doc_title="{doc_title}")),
            ("human", "{reduce_payload}"),
        ]
    )
    reduce_chain = reduce_prompt | structured_llm(
        ConsolidateResult,
        caller="IntraDoc.reduce",
        max_tokens=settings.CONSOLIDATION_MAX_TOKENS,
    )

    def _intradoc(inputs: dict[str, Any]) -> list[dict[str, Any]]:
        text = inputs.get("text") or ""
        doc_title = inputs.get("doc_title") or "Document"
        user_intent = inputs.get("user_intent") or ""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=passage_chunk_size_chars(),
            chunk_overlap=0,
            separators=["\n\n", "\n", " ", ""],
        )
        chunks = splitter.split_text(text.strip()) if text.strip() else [""]
        map_inputs = [
            {
                "doc_title": doc_title,
                "chunk_payload": json.dumps(
                    {
                        "passage_index": i,
                        "user_intent": user_intent,
                        "passage": chunk,
                    },
                    ensure_ascii=False,
                ),
            }
            for i, chunk in enumerate(chunks)
        ]
        mapped: list[PassageExtractResult] = map_chain.batch(map_inputs)
        reduce_payload = json.dumps(
            {
                "user_intent": user_intent,
                "raw_passages": [m.model_dump() for m in mapped],
            },
            ensure_ascii=False,
        )
        consolidated: ConsolidateResult = reduce_chain.invoke(
            {"doc_title": doc_title, "reduce_payload": reduce_payload}
        )
        return _concepts_from_consolidated(consolidated)

    return RunnableLambda(_intradoc)


# --- Stub chains (deterministic, no vLLM) ---


def _stub_supervisor() -> Runnable:
    def _run(inp: dict) -> WorkerName:
        intro = inp.get("introduction")
        if intro is None:
            intro = inp.get("project_scope") or ""
            if intro == "(empty)":
                intro = ""
        project = Project(_id="p", name="p", introduction=intro)
        return keyword_route(inp["text"], inp.get("context") or {}, project)

    return RunnableLambda(_run)


def _stub_conversation() -> Runnable:
    def _run(inp: dict) -> str:
        scope = (inp.get("project_scope") or "").strip()
        prefix = f"[stub] Project scope: {scope[:120]}… " if scope else "[stub] "
        return f"{prefix}You said: {inp['text'][:400]}"

    return RunnableLambda(_run)


def _stub_gist_draft() -> Runnable:
    return RunnableLambda(lambda _: "Here's a gist draft in thread only.")


def _stub_scope() -> Runnable:
    def _run(inp: dict) -> str:
        payload = inp.get("payload") or "{}"
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return ""
        return str(parsed.get("latest_user_message") or "").strip()

    return RunnableLambda(_run)


def _stub_retrieval() -> Runnable:
    def _run(inp: dict) -> str:
        ids = inp.get("highlighted_ids") or []
        return f"[stub] Highlighted {len(ids)} related nodes for: {inp.get('query', '')[:120]}"

    return RunnableLambda(_run)


def _stub_intradoc() -> Runnable:
    def _run(inp: dict) -> list[dict[str, Any]]:
        if _recorded_intradoc:
            return [
                {
                    "concept_id": f"c{i + 1}_{uuid.uuid4().hex[:6]}",
                    "title": r["title"],
                    "description": r.get("description", ""),
                }
                for i, r in enumerate(_recorded_intradoc)
            ]
        text = (inp.get("text") or "").strip()
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=passage_chunk_size_chars(),
            chunk_overlap=0,
        )
        chunks = splitter.split_text(text) if text else [""]
        raw: list[PassageExtractResult] = []
        for i, chunk in enumerate(chunks):
            snippet = re.sub(r"\s+", " ", chunk.strip())[:80]
            raw.append(
                PassageExtractResult(
                    concepts=[
                        PassageConcept(
                            idx=0,
                            title=snippet or f"Passage {i + 1}",
                            description="Stub extract.",
                        )
                    ]
                )
            )
        consolidated = ConsolidateResult(
            doc_description="Stub",
            concepts=[
                CanonicalConcept(
                    title=c.concepts[0].title,
                    description=c.concepts[0].description,
                    passage_indices=[i],
                )
                for i, c in enumerate(raw)
            ],
        )
        return _concepts_from_consolidated(consolidated)

    return RunnableLambda(_run)


@dataclass
class AgentChains:
    supervisor: Runnable
    conversation: Runnable
    gist_draft: Runnable
    project_scope: Runnable
    retrieval_summary: Runnable
    intradoc: Runnable


_override: AgentChains | None = None


def set_chains_override(chains: AgentChains | None) -> None:
    global _override
    _override = chains


def get_chains() -> AgentChains:
    if _override is not None:
        return _override
    if settings.CHAT_LLM_MODE == "live":
        return AgentChains(
            supervisor=_live_supervisor(),
            conversation=_live_conversation(),
            gist_draft=_live_gist_draft(),
            project_scope=_live_scope(),
            retrieval_summary=_live_retrieval_summary(),
            intradoc=_live_intradoc(),
        )
    return AgentChains(
        supervisor=_stub_supervisor(),
        conversation=_stub_conversation(),
        gist_draft=_stub_gist_draft(),
        project_scope=_stub_scope(),
        retrieval_summary=_stub_retrieval(),
        intradoc=_stub_intradoc(),
    )
