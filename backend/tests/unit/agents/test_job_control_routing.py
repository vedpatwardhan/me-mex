import pytest
from app.agents.job_control_routing import (
    detect_job_control_verb,
    is_job_status_inquiry,
    normalize_job_control_decision,
)
from app.llm.schemas import WorkerRoute


@pytest.mark.parametrize(
    "text,expected",
    [
        ("pause the gist job", "pause"),
        ("Please resume background work", "resume"),
        ("cancel that intradoc", "cancel"),
        ("delete the job from the queue", "delete"),
        ("stop the running gist", "cancel"),
    ],
)
def test_detect_job_control_verbs(text, expected):
    assert detect_job_control_verb(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "What is the status of the third paper gist? Just a status check.",
        "Great, how far along is the running gist job?",
        "Is the gist job still running?",
        "What's the progress on the queue?",
    ],
)
def test_status_inquiry_without_control_verbs(text):
    assert is_job_status_inquiry(text) is True
    assert detect_job_control_verb(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "Pause the job and tell me the status",
        "Cancel the gist — what is its status?",
    ],
)
def test_status_phrase_with_control_verb_is_not_pure_status_inquiry(text):
    assert is_job_status_inquiry(text) is False


def test_misrouted_pause_on_status_check_becomes_conversation_status():
    """Mirrors trace 39: Supervisor returned job_control+pause for a status-only question."""
    decision = WorkerRoute(
        worker="job_control",
        intent="job_control",
        dispatch=True,
        target_id="job_542c0faf847b",
        job_action="pause",
    )
    text = (
        "Great, what is the status of the job for the 3rd paper "
        "that you were computing a gist for? Just a status check."
    )
    resolved = normalize_job_control_decision(decision, text)

    assert resolved.worker == "conversation"
    assert resolved.intent == "status"
    assert resolved.dispatch is False
    assert resolved.job_action is None
    assert resolved.target_id is None


@pytest.mark.parametrize(
    "text,action",
    [
        ("Pause the gist for the third paper.", "pause"),
        ("Resume the paused intradoc job.", "resume"),
        ("Cancel the background gist.", "cancel"),
        ("Remove that job from the queue.", "delete"),
    ],
)
def test_explicit_job_control_preserved(text, action):
    decision = WorkerRoute(
        worker="job_control",
        intent="job_control",
        dispatch=True,
        target_id="job_abc",
        job_action="pause" if action != "pause" else "cancel",
    )
    resolved = normalize_job_control_decision(decision, text)

    assert resolved.worker == "job_control"
    assert resolved.intent == "job_control"
    assert resolved.dispatch is True
    assert resolved.job_action == action
    assert resolved.target_id == "job_abc"


def test_approve_utterance_not_job_control():
    decision = WorkerRoute(
        worker="job_control",
        intent="job_control",
        dispatch=True,
        target_id="job_abc",
        job_action="cancel",
    )
    resolved = normalize_job_control_decision(decision, "Approve the gist in the dock.")

    assert resolved.worker == "conversation"
    assert resolved.intent == "conversation"
    assert resolved.dispatch is False
    assert resolved.job_action is None


def test_route_intent_applies_normalizer(project):
    from dataclasses import replace

    from app.agents import workers
    from app.llm import get_chains, set_chains_override
    from langchain_core.runnables import RunnableLambda

    base = get_chains()
    set_chains_override(
        replace(
            base,
            supervisor=RunnableLambda(
                lambda _inputs: WorkerRoute(
                    worker="job_control",
                    intent="job_control",
                    dispatch=True,
                    target_id="job_x",
                    job_action="pause",
                )
            ),
        )
    )

    decision = workers.route_intent(
        "What is the status of the running gist? Status check only.",
        {},
        project,
    )
    assert decision.intent == "status"
    assert decision.worker == "conversation"
