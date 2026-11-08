"""Tests for ingestion throughput helpers and config."""

import json

from app.config import settings
from app.services.ingest_payload import json_dumps_ingest, ingest_context_message_blocks
from app.agents.graph_navigator import GraphNavigator
from app.db import db_engine
from app.models import GraphNode


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


def test_genesis_skip_insufficient_neighbors(monkeypatch):
    project_id = "test_genesis_skip_neighbors"
    genesis = GraphNode(
        _id="concept_genesis",
        node_type="CONCEPT",
        title="Everything",
        project_ids=[project_id],
        metadata={"is_genesis": True, "immutable": False},
    )
    db_engine.upsert_node(genesis)
    agent = GraphNavigator(project_id=project_id)
    events: list = []

    def fake_neighbors(*_a, **_k):
        return [{"id": "n1", "title": "A"}, {"id": "n2", "title": "B"}]

    monkeypatch.setattr(agent, "_neighbor_entries_for_hub", fake_neighbors)
    monkeypatch.setattr(
        "app.agents.graph_navigator.settings.REORG_SKIP_GENESIS_PARTITION_MIN_NEIGHBORS",
        3,
    )

    cmd = agent.build_split_command_for_hub(
        "concept_genesis", project_id=project_id, emitted_events=events
    )
    assert cmd is None
    assert any(e.get("reason") == "genesis_insufficient_neighbors" for e in events)


def test_config_ingest_defaults():
    assert settings.INGEST_EXTRACTION_CONCURRENCY >= 2
    assert settings.INGEST_TRAVERSAL_TOP_K >= 1
    assert settings.HTTPX_MAX_CONNECTIONS >= settings.INGEST_EXTRACTION_CONCURRENCY
