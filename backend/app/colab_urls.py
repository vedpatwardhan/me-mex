"""Resolve Colab inference gateway URLs from COLAB_INFERENCE_BASE_URL."""

from __future__ import annotations

import os


def _normalize_base(url: str) -> str:
    base = url.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3].rstrip("/")
    return base


def colab_inference_configured() -> bool:
    return bool(os.getenv("COLAB_INFERENCE_BASE_URL", "").strip())


def colab_inference_base_url() -> str:
    raw = os.getenv("COLAB_INFERENCE_BASE_URL", "").strip()
    if raw:
        return _normalize_base(raw)
    return "http://localhost:7860"


def colab_vllm_api_base() -> str:
    return f"{colab_inference_base_url().rstrip('/')}/v1"
