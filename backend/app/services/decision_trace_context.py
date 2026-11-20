"""Per-request metadata for decision scorer traces (contextvars)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from app.db import ToolContext


@dataclass(frozen=True)
class DecisionTraceContext:
    project_id: str
    thread_id: str
    scenario: str
    approval_id: str | None = None


_trace_ctx: ContextVar[DecisionTraceContext | None] = ContextVar("decision_trace_ctx", default=None)


def get_decision_trace_context() -> DecisionTraceContext | None:
    return _trace_ctx.get()


@contextmanager
def decision_trace_scope(
    ctx: ToolContext,
    scenario: str,
    *,
    approval_id: str | None = None,
) -> Iterator[None]:
    token = _trace_ctx.set(
        DecisionTraceContext(
            project_id=ctx.project_id,
            thread_id=ctx.thread_id,
            scenario=scenario,
            approval_id=approval_id,
        )
    )
    try:
        yield
    finally:
        _trace_ctx.reset(token)
