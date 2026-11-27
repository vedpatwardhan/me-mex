from app.agents import session_plane
from app.agents.conversation_utterance import UtteranceIntent
from app.services.checkpoints import JsonCheckpointStore


def test_completed_gist_publishes_brief_approval_status(project, tmpdir_checkpoint, monkeypatch):
    monkeypatch.setattr(
        session_plane,
        "invoke_conversation_utterance",
        lambda inp, intent=UtteranceIntent.GIST_FOLLOWUP: (
            "The gist is ready in the dock for review. Approve it there to add it to the graph."
        ),
    )
    monkeypatch.setattr(
        session_plane,
        "_checkpoint",
        JsonCheckpointStore(str(tmpdir_checkpoint)),
    )
    events = []
    monkeypatch.setattr(
        session_plane,
        "publish_session_event",
        lambda _thread_id, event: events.append(event),
    )

    session_plane.observer_ingest_job(
        project_id=project.id,
        thread_id="gist-followup-test",
        job={
            "job_id": "job-gist-followup",
            "worker": "gist",
            "kind": "gist",
            "label": "Give me a short summary of this paper",
            "request_text": "Give me a short summary of this paper",
            "status": "awaiting_approval",
            "approval_id": "approval-gist-followup",
            "project_id": project.id,
            "thread_id": "gist-followup-test",
        },
        worker_output={
            "reply": "A source summary.",
            "source_summary": "A source-grounded summary of the linked paper.",
            "source_title": "Paper from May 2026",
            "source_url": "https://arxiv.org/pdf/2605.11550",
            "approval_id": "approval-gist-followup",
            "graph_write": False,
        },
    )

    followup = next(event for event in events if event.get("type") == "assistant_followup")
    assert followup["text"] == (
        "The gist is ready in the dock for review. Approve it there to add it to the graph."
    )
    assert len(followup["text"].split()) < 25
    assert not any(event.get("type") == "proactive" for event in events)
    transcript = JsonCheckpointStore(str(tmpdir_checkpoint)).load("gist-followup-test")[
        "transcript"
    ]
    assert transcript[-1] == {"role": "assistant", "text": followup["text"]}
