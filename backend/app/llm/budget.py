"""vLLM-aware chunk size for LangChain text splitters."""

from __future__ import annotations

from app.config import settings


def passage_chunk_size_chars() -> int:
    """Max chars per chunk for intra-doc map (model context budget)."""
    max_len = settings.LLM_MODEL_MAX_LEN
    completion = settings.LLM_COMPLETION_RESERVE_TOKENS
    overhead = settings.LLM_PROMPT_OVERHEAD_TOKENS
    cpt = settings.LLM_PASSAGE_CHARS_PER_TOKEN
    safety = max(0.5, min(1.0, settings.LLM_PASSAGE_SAFETY_FACTOR))
    summary_slack = int(settings.INGEST_EXTRACTION_SUMMARY_MAX_CHARS / max(cpt, 1.0))
    input_tokens = max(512, max_len - completion - overhead - summary_slack)
    return max(500, int(input_tokens * cpt * safety))
