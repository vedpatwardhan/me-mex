"""Tests for vLLM-aware passage packing."""

from app.config import settings
from app.services.passage_packing import (
    default_passage_max_chars,
    estimate_prompt_budget,
    pack_document_passages,
)


def test_estimate_prompt_budget_12288_window():
    budget = estimate_prompt_budget(
        model_max_len=12288,
        completion_reserve_tokens=2048,
        prompt_overhead_tokens=2800,
        chars_per_token=3.2,
        safety_factor=1.0,
    )
    summary_slack = int(settings.INGEST_EXTRACTION_SUMMARY_MAX_CHARS / 3.2)
    assert budget["input_token_budget"] == 12288 - 2048 - 2800 - summary_slack
    assert budget["passage_max_chars"] > 20000
    assert budget["passage_max_chars"] < 35000


def test_production_passage_cap_conservative():
    cap = default_passage_max_chars()
    assert 12000 <= cap <= 14500


def test_typical_paper_chunk_counts():
    """~66–87k arXiv PDFs land near 5–7 passages, not 4× huge or 10× tiny."""
    cap = default_passage_max_chars()
    for size in (66_648, 87_036):
        n = size / cap
        assert 4.5 <= n <= 7.5, f"{size} chars at cap {cap} -> {n:.1f} chunks"


def test_default_budget_fits_vllm_context_with_pessimistic_tokenizer():
    """Packed passages should not exceed 12288 when completion reserve is reserved."""
    budget = estimate_prompt_budget()
    worst_passage_tokens = budget["passage_max_chars"] / 2.5
    total = (
        budget["prompt_overhead_tokens"]
        + budget["completion_reserve_tokens"]
        + worst_passage_tokens
    )
    assert total <= budget["model_max_len"] + 64


def test_max_passage_body_chars_smaller_than_default():
    from app.services.passage_packing import max_passage_body_chars

    long_title = "A" * 200
    assert max_passage_body_chars(long_title) < default_passage_max_chars()


def test_default_passage_max_chars_matches_settings():
    assert default_passage_max_chars() == estimate_prompt_budget()["passage_max_chars"]


def test_pack_single_short_note():
    text = "Brief world-model note."
    assert pack_document_passages(text) == [text]


def test_pack_66k_paper_few_chunks():
    section = (
        "We formulate the policy optimization objective over simulated latent rollouts. "
        "The dynamics predictor estimates future embeddings conditioned on candidate action sequences. "
        "Heuristic tree search samples action branches to maximize cumulative discounted rewards.\n\n"
        * 5
    )
    doc_text = "\n\n".join([f"### Section {i}\n{section}" for i in range(50)])
    assert 60000 <= len(doc_text) <= 75000
    cap = default_passage_max_chars()
    chunks = pack_document_passages(doc_text, max_chunk_chars=cap)
    assert 2 <= len(chunks) <= 8
    assert all(len(c) <= cap for c in chunks)
    joined = "\n\n".join(chunks)
    assert len(joined) >= len(doc_text) - 200


def test_pack_respects_max_chunks():
    long_section = (
        "Diffusion policies represent complex multi-modal distributions over continuous action spaces. "
        "By applying denoising diffusion probabilistic models, the agent generates trajectory rollouts. "
        "Residual energy models steer the sampling trajectory toward high-feasibility regions.\n\n"
        * 10
    )
    doc_text = "\n\n".join([f"## Chapter {i}\n{long_section}" for i in range(120)])
    assert len(doc_text) >= 300000
    cap = default_passage_max_chars()
    chunks = pack_document_passages(doc_text, max_chunks=40, max_chunk_chars=cap)
    assert len(chunks) <= 40
    assert len(chunks) >= len(doc_text) // cap - 1
    assert all(len(c) <= cap for c in chunks)


def test_config_ingest_passage_override():
    custom = settings.INGEST_PASSAGE_MAX_CHARS
    if custom:
        chunks = pack_document_passages(
            "x" * (custom * 2 + 100), max_chunk_chars=custom
        )
        assert len(chunks) >= 2
        assert all(len(c) <= custom for c in chunks)
