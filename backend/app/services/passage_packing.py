"""Token-budget passage packing for ingest extraction (vLLM max-model-len aware)."""

from __future__ import annotations

import re
from typing import List

from app.config import settings

CHARS_PER_TOKEN_HEURISTIC = 3.2


def estimate_prompt_budget(
    *,
    model_max_len: int | None = None,
    completion_reserve_tokens: int | None = None,
    prompt_overhead_tokens: int | None = None,
    chars_per_token: float = CHARS_PER_TOKEN_HEURISTIC,
) -> dict[str, int]:
    """
    Estimate safe passage body size (chars) for one extract_concepts_from_passage call.

    Aligns with Colab vLLM --max-model-len (default 12288) minus completion and prompt overhead.
    """
    max_len = model_max_len if model_max_len is not None else settings.LLM_MODEL_MAX_LEN
    completion = (
        completion_reserve_tokens
        if completion_reserve_tokens is not None
        else settings.LLM_COMPLETION_RESERVE_TOKENS
    )
    overhead = (
        prompt_overhead_tokens
        if prompt_overhead_tokens is not None
        else settings.LLM_PROMPT_OVERHEAD_TOKENS
    )
    input_tokens = max(512, max_len - completion - overhead)
    passage_max_chars = max(500, int(input_tokens * chars_per_token))
    return {
        "model_max_len": max_len,
        "completion_reserve_tokens": completion,
        "prompt_overhead_tokens": overhead,
        "input_token_budget": input_tokens,
        "passage_max_chars": passage_max_chars,
    }


def default_passage_max_chars() -> int:
    return estimate_prompt_budget()["passage_max_chars"]


def _atomic_units(text: str, unit_max: int) -> List[str]:
    raw_paragraphs = text.split("\n\n")
    atomic_units: List[str] = []
    for p in raw_paragraphs:
        p_str = p.strip()
        if not p_str:
            continue
        if len(p_str) <= unit_max:
            atomic_units.append(p_str)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", p_str)
        curr_sentence_buf = ""
        for s in sentences:
            if len(curr_sentence_buf) + len(s) + 1 <= unit_max:
                curr_sentence_buf += (" " if curr_sentence_buf else "") + s
            else:
                if curr_sentence_buf:
                    atomic_units.append(curr_sentence_buf)
                curr_sentence_buf = s
        if curr_sentence_buf:
            atomic_units.append(curr_sentence_buf)
    if not atomic_units:
        atomic_units = [text[:unit_max]]
    return atomic_units


def pack_document_passages(
    text: str,
    *,
    max_chunk_chars: int | None = None,
    max_chunks: int = 30,
    min_tail_chars: int | None = None,
) -> List[str]:
    """
    Split document text into the fewest cohesive passages that fit the LLM input budget.

    Objective: ceil(len / max_chunk_chars) packs — no tier-based minimum chunk counts.
    """
    if not text:
        return []

    text = text.strip()
    if not text:
        return []

    chunk_size = (
        max_chunk_chars if max_chunk_chars is not None else default_passage_max_chars()
    )
    min_tail = (
        min_tail_chars
        if min_tail_chars is not None
        else settings.INGEST_PASSAGE_TARGET_MIN_CHARS
    )

    if len(text) <= chunk_size:
        return [text]

    atomic_units = _atomic_units(text, chunk_size)
    chunks: List[str] = []
    curr = ""
    for unit in atomic_units:
        if len(curr) + len(unit) + 2 <= chunk_size:
            curr += ("\n\n" if curr else "") + unit
        else:
            if curr:
                chunks.append(curr.strip())
            curr = unit
    if curr.strip():
        chunks.append(curr.strip())

    if not chunks:
        chunks = [text[:chunk_size]]

    while len(chunks) > max_chunks:
        min_idx = 0
        min_combined_len = float("inf")
        for i in range(len(chunks) - 1):
            comb = len(chunks[i]) + len(chunks[i + 1])
            if comb < min_combined_len:
                min_combined_len = comb
                min_idx = i
        chunks[min_idx] = chunks[min_idx] + "\n\n" + chunks[min_idx + 1]
        chunks.pop(min_idx + 1)

    # merge tiny tail into previous chunk when possible
    if len(chunks) >= 2 and len(chunks[-1]) < min_tail:
        if len(chunks[-2]) + len(chunks[-1]) + 2 <= chunk_size:
            chunks[-2] = chunks[-2] + "\n\n" + chunks[-1]
            chunks.pop()

    oversized = [c for c in chunks if len(c) > chunk_size]
    if oversized:
        fixed: List[str] = []
        for c in chunks:
            if len(c) <= chunk_size:
                fixed.append(c)
            else:
                fixed.extend(_split_oversized(c, chunk_size))
        chunks = fixed
        while len(chunks) > max_chunks:
            min_idx = min(
                range(len(chunks) - 1),
                key=lambda i: len(chunks[i]) + len(chunks[i + 1]),
            )
            if len(chunks[min_idx]) + len(chunks[min_idx + 1]) + 2 > chunk_size:
                break
            chunks[min_idx] = chunks[min_idx] + "\n\n" + chunks[min_idx + 1]
            chunks.pop(min_idx + 1)

    return [c for c in chunks if c.strip()]


def _split_oversized(chunk: str, chunk_size: int) -> List[str]:
    parts: List[str] = []
    start = 0
    while start < len(chunk):
        end = min(start + chunk_size, len(chunk))
        if end < len(chunk):
            split_pos = chunk.rfind("\n\n", start, end)
            if split_pos <= start:
                split_pos = chunk.rfind(". ", start, end)
                if split_pos > start:
                    split_pos += 1
            if split_pos > start:
                end = split_pos
        piece = chunk[start:end].strip()
        if piece:
            parts.append(piece)
        start = end if end > start else start + chunk_size
    return parts or [chunk[:chunk_size]]
