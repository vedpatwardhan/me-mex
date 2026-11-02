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
    MAX_TRAVERSAL_DEPTH: int = int(os.getenv("MAX_TRAVERSAL_DEPTH", "4"))
    REACHABILITY_HOP_K: int = int(os.getenv("REACHABILITY_HOP_K", "3"))
    MAX_UPWARD_REORG_ITERATIONS: int = int(
        os.getenv("MAX_UPWARD_REORG_ITERATIONS", "5")
    )


settings = Settings()
