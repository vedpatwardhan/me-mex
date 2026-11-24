from app.agents.workflow_routing import (
    is_workflow_next_steps_inquiry,
    normalize_post_scope_workflow_decision,
    supervisor_reply_redirects_to_scope_review,
)
from app.llm.schemas import WorkerRoute


def test_detects_workflow_next_steps_phrases():
    assert is_workflow_next_steps_inquiry("Hey there, what's next?")
    assert is_workflow_next_steps_inquiry("I'd like to proceed with the next steps, what's next.")
    assert not is_workflow_next_steps_inquiry("Pause the gist job.")


def test_scope_review_supervisor_reply_is_detected():
    reply = "Your scope is committed. Explore the proposed scope in the dock and proceed with next steps."
    assert supervisor_reply_redirects_to_scope_review(reply)


def test_clears_bad_supervisor_reply_after_scope_complete():
    decision = WorkerRoute(
        worker="conversation",
        intent="status",
        dispatch=False,
        reply="Explore the proposed scope in the dock.",
    )
    out = normalize_post_scope_workflow_decision(
        decision,
        "what's next?",
        scope_complete=True,
    )
    assert out.intent == "conversation"
    assert out.reply is None


def test_keeps_good_supervisor_reply_when_not_scope_redirect():
    decision = WorkerRoute(
        worker="conversation",
        intent="conversation",
        dispatch=False,
        reply="Share a paper link and we can add the first ROOT to your graph.",
    )
    out = normalize_post_scope_workflow_decision(
        decision,
        "what's next?",
        scope_complete=True,
    )
    assert out.reply == decision.reply


def test_no_change_when_scope_incomplete():
    decision = WorkerRoute(worker="conversation", intent="conversation", dispatch=False, reply="Hi")
    out = normalize_post_scope_workflow_decision(decision, "what's next?", scope_complete=False)
    assert out.reply == "Hi"
