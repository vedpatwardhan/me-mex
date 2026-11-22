"""Normalize assistant text for TTS (abbreviations, light cleanup)."""

from __future__ import annotations

import re

_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\be\.g\.", re.IGNORECASE), "for example,"),
    (re.compile(r"\bi\.e\.", re.IGNORECASE), "that is,"),
    (re.compile(r"\betc\.", re.IGNORECASE), "and so on,"),
    (re.compile(r"\bvs\.", re.IGNORECASE), "versus"),
    (re.compile(r"\bw/", re.IGNORECASE), "with "),
)

_LEADING_LIST = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)


def speech_friendly(text: str) -> str:
    """Expand common abbreviations and trim list markers for speakable TTS."""
    if not text:
        return text
    out = text
    for pattern, replacement in _REPLACEMENTS:
        out = pattern.sub(replacement, out)
    out = _LEADING_LIST.sub("", out)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
