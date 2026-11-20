"""Parse SSE bodies from FastAPI TestClient streaming responses."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


def iter_sse_data(response) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from ``data: …`` lines (str or bytes per httpx/starlette)."""
    for line in response.iter_lines():
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        if not line or not line.startswith("data: "):
            continue
        yield json.loads(line[6:])
