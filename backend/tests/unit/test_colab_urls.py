import os

import pytest
from app.colab_urls import colab_inference_base_url, colab_vllm_api_base


@pytest.fixture(autouse=True)
def _clear_colab_env(monkeypatch):
    monkeypatch.delenv("COLAB_INFERENCE_BASE_URL", raising=False)


def test_single_base_url():
    os.environ["COLAB_INFERENCE_BASE_URL"] = "https://tunnel.example.com"
    assert colab_inference_base_url() == "https://tunnel.example.com"
    assert colab_vllm_api_base() == "https://tunnel.example.com/v1"


def test_strips_trailing_v1_if_mistakenly_set():
    os.environ["COLAB_INFERENCE_BASE_URL"] = "https://tunnel.example.com/v1"
    assert colab_inference_base_url() == "https://tunnel.example.com"
    assert colab_vllm_api_base() == "https://tunnel.example.com/v1"
