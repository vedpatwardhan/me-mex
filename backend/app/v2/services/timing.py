"""Per-tool latency logging."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger("memex.v2.tools")
F = TypeVar("F", bound=Callable)


def timed_tool(fn: F) -> F:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            ms = (time.perf_counter() - start) * 1000
            logger.info("tool=%s latency_ms=%.2f", fn.__name__, ms)

    return wrapper  # type: ignore[return-value]
