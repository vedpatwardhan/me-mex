from dataclasses import replace

from app.agents import session_plane
from app.llm import get_chains, set_chains_override
from app.services.checkpoints import JsonCheckpointStore
from langchain_core.runnables import RunnableLambda


def test_completed_gist_is_returned_to_conversation_and_published(
    project, tmpdir_checkpoint, monkeypatch
):
    monkeypatch.setattr(
        session_plane,
        "_checkpoint",
        JsonCheckpointStore(str(tmpdir_checkpoint)),
    )
    events = []
    conversation_inputs = []

    def answer_from_worker_result(inputs):
        conversation_inputs.append(inputs)
        return "The supplied paper studies its stated model and reports its main result."

    base = get_chains()
    set_chains_override(replace(base, conversation=RunnableLambda(answer_from_worker_result)))
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
            "status": "done",
            "project_id": project.id,
            "thread_id": "gist-followup-test",
        },
        worker_output={
            "reply": "A source summary.",
            "source_summary": "A source-grounded summary of the linked paper.",
            "source_title": "Paper from May 2026",
            "source_url": "https://arxiv.org/pdf/2605.11550",
            "graph_write": False,
        },
    )

    followup = next(event for event in events if event.get("type") == "assistant_followup")
    assert followup["text"] == (
        "The supplied paper studies its stated model and reports its main result."
    )
    assert "A source-grounded summary of the linked paper." in conversation_inputs[0]["text"]
    assert "2605.11550" in conversation_inputs[0]["text"]
    assert not any(event.get("type") == "proactive" for event in events)
    transcript = JsonCheckpointStore(str(tmpdir_checkpoint)).load("gist-followup-test")[
        "transcript"
    ]
    assert transcript[-1] == {"role": "assistant", "text": followup["text"]}
