import os
from pathlib import Path

from dotenv import load_dotenv

from app.colab_urls import (
    colab_inference_base_url,
    colab_inference_configured,
    colab_vllm_api_base,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

env_file = os.getenv("ENV_FILE")
if env_file:
    load_dotenv(dotenv_path=Path(env_file))
elif os.getenv("TESTING") == "1":
    load_dotenv(dotenv_path=BACKEND_DIR / ".env.test")
else:
    load_dotenv(dotenv_path=BACKEND_DIR / ".env")


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def _optional_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return int(raw)


class Settings:
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")

    @property
    def DB_NAME(self) -> str:
        return os.getenv("DB_NAME", "me-mex")

    # Remote inference — one gateway host; code appends /v1 or /stt|/tts paths
    @property
    def COLAB_INFERENCE_BASE_URL(self) -> str:
        return colab_inference_base_url()

    @property
    def colab_inference_configured(self) -> bool:
        return colab_inference_configured()

    @property
    def colab_vllm_api_base(self) -> str:
        return colab_vllm_api_base()

    LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "mistralai/Ministral-3-8B-Reasoning-2512")
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "180.0"))
    # stub | live — chat completions from worker agents (pytest: backend/.env.test)
    CHAT_LLM_MODE: str = os.getenv("CHAT_LLM_MODE", "live").lower()
    # mock | live — gateway reranker POST /decision/score (pytest: backend/.env.test)
    DECISION_SCORER_MODE: str = os.getenv("DECISION_SCORER_MODE", "live").lower()

    # Token / context budgets (passage packing + agent calls)
    LLM_MODEL_MAX_LEN: int = int(os.getenv("LLM_MODEL_MAX_LEN", "12288"))
    LLM_COMPLETION_RESERVE_TOKENS: int = int(os.getenv("LLM_COMPLETION_RESERVE_TOKENS", "2048"))
    LLM_PROMPT_OVERHEAD_TOKENS: int = int(os.getenv("LLM_PROMPT_OVERHEAD_TOKENS", "4000"))
    LLM_PASSAGE_CHARS_PER_TOKEN: float = float(os.getenv("LLM_PASSAGE_CHARS_PER_TOKEN", "3.0"))
    LLM_PASSAGE_SAFETY_FACTOR: float = float(os.getenv("LLM_PASSAGE_SAFETY_FACTOR", "0.86"))
    INGEST_EXTRACTION_SUMMARY_MAX_CHARS: int = int(
        os.getenv("INGEST_EXTRACTION_SUMMARY_MAX_CHARS", "2400")
    )
    INGEST_PASSAGE_MAX_CHARS: int | None = _optional_int("INGEST_PASSAGE_MAX_CHARS")
    INGEST_PASSAGE_TARGET_MIN_CHARS: int = int(os.getenv("INGEST_PASSAGE_TARGET_MIN_CHARS", "3000"))
    LLM_COMPLETION_MAX_TOKENS: int = int(os.getenv("LLM_COMPLETION_MAX_TOKENS", "2048"))
    CONSOLIDATION_MAX_TOKENS: int = int(os.getenv("CONSOLIDATION_MAX_TOKENS", "3072"))
    CHAT_COMPLETION_MAX_TOKENS: int = int(os.getenv("CHAT_COMPLETION_MAX_TOKENS", "1024"))
    VOICE_FOREGROUND_MAX_TOKENS: int = int(os.getenv("VOICE_FOREGROUND_MAX_TOKENS", "220"))
    WORKFLOW_AGENT_MAX_TOKENS: int = int(os.getenv("WORKFLOW_AGENT_MAX_TOKENS", "256"))
    VOICE_KEYWORD_DISPATCH: bool = _env_bool("VOICE_KEYWORD_DISPATCH", "false")
    INGEST_EXTRACTION_CONCURRENCY: int = int(os.getenv("INGEST_EXTRACTION_CONCURRENCY", "2"))

    # Graph traversal (RetrievalWorker BFS)
    MAX_TRAVERSAL_DEPTH: int = int(os.getenv("MAX_TRAVERSAL_DEPTH", "5"))
    RETRIEVAL_TRAVERSAL_TOP_K: int = int(os.getenv("RETRIEVAL_TRAVERSAL_TOP_K", "3"))
    DEGREE_THRESHOLD: int = int(os.getenv("DEGREE_THRESHOLD", "7"))

    HTTPX_MAX_CONNECTIONS: int = int(os.getenv("HTTPX_MAX_CONNECTIONS", "20"))
    HTTPX_MAX_KEEPALIVE: int = int(os.getenv("HTTPX_MAX_KEEPALIVE", "10"))

    @property
    def CHECKPOINTS_DIR(self) -> str:
        return os.getenv("CHECKPOINTS_DIR", str(BACKEND_DIR / "data" / "checkpoints"))

    @property
    def DECISION_TRAINING_DIR(self) -> str:
        return os.getenv(
            "DECISION_TRAINING_DIR",
            str(BACKEND_DIR / "data" / "decision_training"),
        )

    @property
    def DECISION_TRACE_DIR(self) -> str:
        return os.getenv("DECISION_TRACE_DIR", str(BACKEND_DIR / "logs" / "decision_traces"))

    DECISION_TRACE_ENABLED: bool = _env_bool(
        "DECISION_TRACE_ENABLED",
        "true" if os.getenv("TESTING") != "1" else "false",
    )


settings = Settings()
