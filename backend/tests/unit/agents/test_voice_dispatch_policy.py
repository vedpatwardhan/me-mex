import asyncio
import threading

import pytest
from app.agents.voice_dispatch import (
    needs_voice_dispatch,
    normalize_link_decision,
    resolve_voice_route_async,
)
from app.llm.schemas import WorkerRoute


@pytest.mark.voice_plane
@pytest.mark.parametrize(
    "decision,voice,expected",
    [
        (WorkerRoute(worker="conversation", intent="conversation", dispatch=False), True, False),
        (WorkerRoute(worker="retrieval", intent="retrieval", dispatch=True), True, True),
        (WorkerRoute(worker="intradoc", intent="source_analysis", dispatch=True), True, True),
        (WorkerRoute(worker="conversation", intent="conversation", dispatch=False), False, False),
    ],
)
def test_needs_voice_dispatch(decision, voice, expected):
    assert needs_voice_dispatch(decision, voice_turn=voice) is expected


@pytest.mark.voice_plane
def test_project_scope_dispatch_comes_from_supervisor_decision():
    proposal = WorkerRoute(worker="project_scope", intent="scope_save", dispatch=True)
    conversation = WorkerRoute(worker="project_scope", intent="scope_conversation", dispatch=False)
    assert needs_voice_dispatch(proposal, voice_turn=True) is True
    assert needs_voice_dispatch(conversation, voice_turn=True) is False
    assert needs_voice_dispatch(proposal, voice_turn=False) is False


@pytest.mark.voice_plane
def test_link_normalization_uses_current_root_and_removes_reversed_root_target():
    decision = WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        root_id="genesis",
        target_id="genesis",
        target_ids=["older-root"],
    )
    context = {
        "graph_candidates": [
            {"id": "older-root", "title": "Older paper", "node_kind": "ROOT"},
            {"id": "current-root", "title": "Current paper", "node_kind": "ROOT"},
            {"id": "genesis", "title": "Genesis", "node_kind": "CONCEPT_M"},
        ],
        "routing_memory": {
            "current_source": {"worker": "gist", "root_id": "current-root"},
        },
    }

    resolved = normalize_link_decision(decision, context)

    assert resolved.worker == "link"
    assert resolved.root_id == "current-root"
    assert resolved.target_ids == ["genesis"]


@pytest.mark.voice_plane
def test_link_normalization_clarifies_when_multiple_roots_have_no_current_source():
    decision = WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        target_id="genesis",
    )
    context = {
        "graph_candidates": [
            {"id": "root-a", "title": "Paper A", "node_kind": "ROOT"},
            {"id": "root-b", "title": "Paper B", "node_kind": "ROOT"},
            {"id": "genesis", "title": "Genesis", "node_kind": "CONCEPT_M"},
        ],
        "routing_memory": {},
    }

    resolved = normalize_link_decision(decision, context)

    assert resolved.worker == "conversation"
    assert resolved.dispatch is False
    assert resolved.source_error == "link_resolution"
    assert "Paper A" in (resolved.content or "")
    assert "Paper B" in (resolved.content or "")


@pytest.mark.voice_plane
def test_link_does_not_fall_back_to_an_older_root_for_unrooted_current_source():
    decision = WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        target_id="genesis",
    )
    context = {
        "graph_candidates": [
            {"id": "older-root", "title": "Older paper", "node_kind": "ROOT"},
            {"id": "genesis", "title": "Genesis", "node_kind": "CONCEPT_M"},
        ],
        "routing_memory": {
            "focus_root": {"id": "older-root", "title": "Older paper", "node_kind": "ROOT"},
            "current_source": {
                "worker": "intradoc",
                "title": "New paper",
                "source_url": "https://example.test/new-paper.pdf",
                "root_id": "",
            },
        },
    }

    resolved = normalize_link_decision(decision, context)

    assert resolved.worker == "conversation"
    assert resolved.dispatch is False
    assert resolved.source_error == "link_resolution"
    assert "Available ROOTs" in (resolved.content or "")
    assert "Older paper" in (resolved.content or "")
    assert "does not have a ROOT" in (resolved.content or "")


@pytest.mark.voice_plane
def test_link_explicit_dawn_while_other_gist_unrooted_current_source():
    """E2E mirror: supervisor swap while gist for another paper is in flight."""
    decision = WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        target_id="genesis_global",
        target_ids=["root_dawn"],
    )
    context = {
        "graph_candidates": [
            {"id": "genesis_global", "title": "Genesis", "node_kind": "CONCEPT_M"},
            {
                "id": "root_dawn",
                "title": "The DAWN of World-Action Interactive Models",
                "node_kind": "ROOT",
            },
        ],
        "routing_memory": {
            "focus_root": {
                "id": "root_dawn",
                "title": "The DAWN of World-Action Interactive Models",
                "node_kind": "ROOT",
                "source_uri": "https://arxiv.org/pdf/2605.11550",
            },
            "current_source": {
                "worker": "gist",
                "source_url": "https://arxiv.org/pdf/2610.20951",
                "title": "",
                "root_id": "",
            },
        },
    }

    resolved = normalize_link_decision(decision, context)

    assert resolved.worker == "link"
    assert resolved.root_id == "root_dawn"
    assert resolved.target_ids == ["genesis_global"]


@pytest.mark.voice_plane
def test_link_utterance_title_match_single_root():
    decision = WorkerRoute(
        worker="link",
        intent="link",
        dispatch=True,
        target_id="genesis_global",
    )
    context = {
        "graph_candidates": [
            {"id": "genesis_global", "title": "Genesis", "node_kind": "CONCEPT_M"},
            {
                "id": "root_dawn",
                "title": "The DAWN of World-Action Interactive Models",
                "node_kind": "ROOT",
            },
            {
                "id": "root_lev",
                "title": "LEV: Thinking Fast and Deep",
                "node_kind": "ROOT",
            },
        ],
        "routing_memory": {
            "current_source": {
                "worker": "gist",
                "source_url": "https://arxiv.org/pdf/2610.20951",
                "title": "LEV",
                "root_id": "",
            },
        },
    }

    resolved = normalize_link_decision(
        decision.model_copy(update={"root_id": "root_dawn"}),
        context,
        utterance="Connect the dawn root node to the genesis node.",
    )

    assert resolved.worker == "link"
    assert resolved.root_id == "root_dawn"
    assert resolved.target_ids == ["genesis_global"]


@pytest.mark.voice_plane
@pytest.mark.asyncio
async def test_voice_supervisor_call_does_not_block_event_loop(monkeypatch):
    from app.agents import voice_dispatch

    started = threading.Event()
    release = threading.Event()

    def slow_route(**_kwargs):
        started.set()
        assert release.wait(timeout=2)
        return (
            WorkerRoute(worker="conversation", intent="conversation", dispatch=False),
            "hi",
            False,
        )

    monkeypatch.setattr(voice_dispatch, "resolve_voice_route", slow_route)
    task = asyncio.create_task(resolve_voice_route_async())
    assert await asyncio.to_thread(started.wait, 1)

    heartbeat = asyncio.Event()
    asyncio.get_running_loop().call_soon(heartbeat.set)
    await asyncio.wait_for(heartbeat.wait(), timeout=0.1)
    release.set()
    await task
