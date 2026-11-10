"""Tests for ingestion throughput helpers and config."""

import json

from app.config import settings
from app.services.ingest_payload import json_dumps_ingest, ingest_context_message_blocks


def test_json_dumps_ingest_compact():
    payload = {"a": 1, "b": [2, 3]}
    out = json_dumps_ingest(payload)
    if settings.INGEST_JSON_COMPACT:
        assert "\n" not in out
        assert json.loads(out) == payload


def test_ingest_context_prefers_summary(monkeypatch):
    monkeypatch.setattr(settings, "INGEST_USE_ROLLING_SUMMARY", True)
    blocks = ingest_context_message_blocks(
        "ingest this paper",
        rolling_summary="User cares about world models.",
        chat_history=[{"role": "user", "content": "old"}],
    )
    assert any("rolling summary" in b.get("content", "").lower() for b in blocks)
    assert blocks[-1]["content"] == "ingest this paper"


def test_config_ingest_defaults():
    assert settings.INGEST_EXTRACTION_CONCURRENCY >= 2
    assert settings.INGEST_EXTRACTION_CONCURRENCY <= 8
    assert settings.INGEST_TRAVERSAL_TOP_K >= 1
    assert settings.LLM_MODEL_MAX_LEN == 12288
    assert settings.HTTPX_MAX_CONNECTIONS >= settings.INGEST_EXTRACTION_CONCURRENCY


def test_config_ingest_llm_speed_defaults():
    assert settings.REORG_PARTITION_MAX_TOKENS == 3072
    assert settings.COLLECTIVE_LINKING_MAX_TOKENS == 2048
    assert settings.SUBGRAPH_EXPANSION_MAX_TOKENS == 512
    assert settings.GENERALIZATION_MAX_TOKENS == 1536
    assert settings.INGEST_TRAVERSAL_TOP_K == 1
    assert settings.ingest_traversal_max_depth == 3
