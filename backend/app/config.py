import os
from pathlib import Path
from dotenv import load_dotenv

# Path to backend directory and root directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent

# Determine environment: check ENV_FILE or test mode
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

    COLAB_VLLM_URL: str = os.getenv("COLAB_VLLM_URL", "http://localhost:8000/v1")
    LLM_MODEL_NAME: str = os.getenv(
        "LLM_MODEL_NAME", "mistralai/Ministral-3-8B-Reasoning-2512"
    )
    LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "180.0"))

    DEGREE_THRESHOLD: int = int(os.getenv("DEGREE_THRESHOLD", "7"))
    MIN_CLUSTER_SIZE: int = int(os.getenv("MIN_CLUSTER_SIZE", "2"))
    MAX_TRAVERSAL_DEPTH: int = int(os.getenv("MAX_TRAVERSAL_DEPTH", "5"))
    REACHABILITY_HOP_K: int = int(os.getenv("REACHABILITY_HOP_K", "3"))
    MAX_UPWARD_REORG_ITERATIONS: int = int(
        os.getenv("MAX_UPWARD_REORG_ITERATIONS", "5")
    )
    REORG_PARTITION_MAX_TOKENS: int = int(
        os.getenv("REORG_PARTITION_MAX_TOKENS", "6144")
    )

    INGEST_EXTRACTION_CONCURRENCY: int = int(
        os.getenv("INGEST_EXTRACTION_CONCURRENCY", "4")
    )
    INGEST_JSON_COMPACT: bool = _env_bool("INGEST_JSON_COMPACT", "true")
    INGEST_USE_ROLLING_SUMMARY: bool = _env_bool("INGEST_USE_ROLLING_SUMMARY", "true")
    CHAT_SUMMARY_MAX_CHARS: int = int(os.getenv("CHAT_SUMMARY_MAX_CHARS", "4000"))
    CHAT_SUMMARY_REFRESH_MIN_TURNS: int = int(
        os.getenv("CHAT_SUMMARY_REFRESH_MIN_TURNS", "4")
    )
    INGEST_STRUCTURED_CHAT_HISTORY_TURNS: int = int(
        os.getenv("INGEST_STRUCTURED_CHAT_HISTORY_TURNS", "2")
    )
    INGEST_TRAVERSAL_MAX_DEPTH: int | None = _optional_int("INGEST_TRAVERSAL_MAX_DEPTH")
    INGEST_TRAVERSAL_TOP_K: int = int(os.getenv("INGEST_TRAVERSAL_TOP_K", "2"))
    RETRIEVAL_TRAVERSAL_MAX_DEPTH: int | None = _optional_int(
        "RETRIEVAL_TRAVERSAL_MAX_DEPTH"
    )
    RETRIEVAL_TRAVERSAL_TOP_K: int | None = _optional_int("RETRIEVAL_TRAVERSAL_TOP_K")
    RETRIEVAL_CONTEXT_MAX_CHARS: int = int(
        os.getenv("RETRIEVAL_CONTEXT_MAX_CHARS", "48000")
    )
    RETRIEVAL_RELEVANCE_FILTER: bool = _env_bool("RETRIEVAL_RELEVANCE_FILTER", "true")
    # Upper bound on completion tokens for chat/completions (vLLM API field; not input clipping).
    LLM_COMPLETION_MAX_TOKENS: int = int(os.getenv("LLM_COMPLETION_MAX_TOKENS", "2048"))
    # vLLM --max-model-len (Colab default 12288); drives passage/traversal saturation.
    LLM_MODEL_MAX_LEN: int = int(os.getenv("LLM_MODEL_MAX_LEN", "12288"))
    LLM_COMPLETION_RESERVE_TOKENS: int = int(
        os.getenv("LLM_COMPLETION_RESERVE_TOKENS", "2048")
    )
    LLM_PROMPT_OVERHEAD_TOKENS: int = int(
        os.getenv("LLM_PROMPT_OVERHEAD_TOKENS", "2800")
    )
    INGEST_PASSAGE_MAX_CHARS: int | None = _optional_int("INGEST_PASSAGE_MAX_CHARS")
    INGEST_PASSAGE_TARGET_MIN_CHARS: int = int(
        os.getenv("INGEST_PASSAGE_TARGET_MIN_CHARS", "3000")
    )
    TRAVERSAL_INPUT_MAX_CHARS: int = int(os.getenv("TRAVERSAL_INPUT_MAX_CHARS", "9000"))
    GENESIS_TRAVERSAL_MAX_CHARS: int = int(
        os.getenv("GENESIS_TRAVERSAL_MAX_CHARS", "1500")
    )

    HTTPX_MAX_CONNECTIONS: int = int(os.getenv("HTTPX_MAX_CONNECTIONS", "20"))
    HTTPX_MAX_KEEPALIVE: int = int(os.getenv("HTTPX_MAX_KEEPALIVE", "10"))

    REORG_PARTITION_ENABLE_REASONING: bool = _env_bool(
        "REORG_PARTITION_ENABLE_REASONING", "false"
    )


settings = Settings()
