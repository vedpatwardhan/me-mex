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
    ProjectScopeResult,
    WorkerRoute,
)
from app.models import Project
from app.prompts import load_prompt

STUB_CONCEPTS = [
    {"concept_id": "c1", "title": "Main claim", "description": "Extracted concept."},
]


def _intradoc_from_recorded(text: str) -> dict[str, Any] | None:
    if not _recorded_intradoc:
        return None
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=passage_chunk_size_chars(),
        chunk_overlap=0,
    )
    chunks = splitter.split_text(text.strip()) if text.strip() else [""]
    concepts = [
        {
            "concept_id": f"c{i + 1}_{uuid.uuid4().hex[:6]}",
            "title": r["title"],
            "description": r.get("description", ""),
            "passage_indices": r.get("passage_indices") or list(range(len(chunks))),
        }
        for i, r in enumerate(_recorded_intradoc)
    ]
    return {
        "doc_description": "Recorded document summary.",
        "doc_type": "paper",
        "concepts": concepts,
        "passages": [{"passage_index": i, "text": chunk} for i, chunk in enumerate(chunks)],
    }


_recorded_intradoc: list[dict[str, str]] | None = None


def set_recorded_intradoc(rows: list[dict[str, str]] | None) -> None:
    global _recorded_intradoc
    _recorded_intradoc = rows


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
                "passage_indices": sorted(set(c.passage_indices)),
            }
        )
    return out


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

    def _run(inp: dict) -> WorkerRoute:
        max_tokens = int(inp.get("supervisor_max_tokens") or 512)
        chain = prompt | structured_llm(
            WorkerRoute,
            caller="Supervisor.classify",
            max_tokens=max_tokens,
            max_retries=3,
        )
        return chain.invoke(inp)

    return RunnableLambda(_run)


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
            ("system", load_prompt("gist_draft", project_scope="{project_scope}")),
            (
                "human",
                (
                    "Summary stage: {summary_stage}\nSource title: {source_title}\n"
                    "Source URL: {source_url}\n\nExtracted source text:\n{text}"
                ),
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
    return prompt | structured_llm(ProjectScopeResult, caller="ProjectScope", max_tokens=768)


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
        max_retries=1,
    )

    def _intradoc(inputs: dict[str, Any]) -> dict[str, Any]:
        text = inputs.get("text") or ""
        recorded = _intradoc_from_recorded(text)
        if recorded is not None:
            return recorded
        doc_title = inputs.get("doc_title") or "Document"
        user_intent = inputs.get("user_intent") or ""
        checkpoint = inputs.get("checkpoint")
        if callable(checkpoint):
            checkpoint()
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
        concurrency = max(1, settings.INGEST_EXTRACTION_CONCURRENCY)
        raw_concepts: list[dict[str, Any]] = []
        for start in range(0, len(map_inputs), concurrency):
            if callable(checkpoint):
                checkpoint()
            mapped: list[PassageExtractResult] = map_chain.batch(
                map_inputs[start : start + concurrency],
                config={"max_concurrency": concurrency},
            )
            for offset, result in enumerate(mapped):
                passage_index = start + offset
                raw_concepts.extend(
                    {
                        "raw_concept_id": f"{passage_index}:{concept.idx}",
                        "title": concept.title,
                        "description": concept.description,
                        "passage_indices": [passage_index],
                    }
                    for concept in result.concepts
                )
            if callable(checkpoint):
                checkpoint()

        def reduce_group(
            concepts: list[dict[str, Any]], section_summaries: list[str]
        ) -> ConsolidateResult:
            if callable(checkpoint):
                checkpoint()
            payload = json.dumps(
                {
                    "user_intent": user_intent,
                    "section_summaries": section_summaries,
                    "raw_concepts": concepts,
                },
                ensure_ascii=False,
            )
            result: ConsolidateResult = reduce_chain.invoke(
                {"doc_title": doc_title, "reduce_payload": payload}
            )
            if callable(checkpoint):
                checkpoint()
            return result

        if not raw_concepts:
            consolidated = ConsolidateResult(doc_description="", concepts=[])
        else:
            current = raw_concepts
            group_size = 12
            while len(current) > group_size:
                reduced_groups: list[ConsolidateResult] = []
                for start in range(0, len(current), group_size):
                    reduced_groups.append(reduce_group(current[start : start + group_size], []))
                current = [
                    concept
                    for group in reduced_groups
                    for concept in _concepts_from_consolidated(group)
                ]
            consolidated = reduce_group(current, [])

        return {
            "doc_description": consolidated.doc_description,
            "doc_type": consolidated.doc_type,
            "concepts": _concepts_from_consolidated(consolidated),
            "passages": [{"passage_index": i, "text": chunk} for i, chunk in enumerate(chunks)],
        }

    return RunnableLambda(_intradoc)


# --- Stub chains (deterministic, no vLLM) ---


def _stub_supervisor() -> Runnable:
    from app.llm.stub_routing import keyword_route

    def _run(inp: dict) -> WorkerRoute:
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
    return RunnableLambda(lambda inp: (inp.get("text") or "")[:400])


def _stub_scope() -> Runnable:
    def _run(inp: dict) -> ProjectScopeResult:
        payload = inp.get("payload") or "{}"
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        baseline = str(parsed.get("baseline_proposal") or "").strip()
        latest = str(parsed.get("latest_user_message") or "").strip()
        force_replace = bool(parsed.get("force_scope_rewrite"))
        revision_mode = "replace" if force_replace or not baseline else "incremental"
        proposed = latest if revision_mode == "replace" else f"{baseline}\n\n{latest}"
        return ProjectScopeResult(
            revision_mode=revision_mode,
            proposed_introduction=proposed.strip(),
        )

    return RunnableLambda(_run)


def _stub_retrieval() -> Runnable:
    def _run(inp: dict) -> str:
        ids = inp.get("highlighted_ids") or []
        return f"[stub] Highlighted {len(ids)} related nodes for: {inp.get('query', '')[:120]}"

    return RunnableLambda(_run)


def _stub_intradoc() -> Runnable:
    def _run(inp: dict) -> dict[str, Any]:
        text = (inp.get("text") or "").strip()
        recorded = _intradoc_from_recorded(text)
        if recorded is not None:
            return recorded
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
        return {
            "doc_description": consolidated.doc_description,
            "doc_type": consolidated.doc_type,
            "concepts": _concepts_from_consolidated(consolidated),
            "passages": [{"passage_index": i, "text": chunk} for i, chunk in enumerate(chunks)],
        }

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


def is_chains_overridden() -> bool:
    return _override is not None


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
