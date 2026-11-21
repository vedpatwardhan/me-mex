"""Heuristics for dialogue-only voice turns (no worker dispatch)."""

from __future__ import annotations

import re

_CHITCHAT_PHRASES = frozenset(
    {
        "what's next",
        "what is next",
        "whats next",
        "how are you",
        "how's your day",
        "how is your day",
        "how was your day",
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
    }
)

_STATUS_ASK = re.compile(
    r"\b(status|progress|queue|what(?:'s| is) (?:running|in the queue))\b",
    re.IGNORECASE,
)


def is_dialogue_only_utterance(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if len(t) < 30:
        return True
    low = t.lower().rstrip(".!?")
    if low in _CHITCHAT_PHRASES:
        return True
    for phrase in _CHITCHAT_PHRASES:
        if low == phrase or low.startswith(phrase + " "):
            return True
    if _STATUS_ASK.search(t):
        return False
    return bool(
        t.endswith("?")
        and low.startswith(("how ", "what ", "why ", "when ", "where ", "who ", "are you", "is it"))
    )


def user_asked_for_status(text: str) -> bool:
    return bool(_STATUS_ASK.search(text or ""))
