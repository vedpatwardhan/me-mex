import os
from functools import lru_cache

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Loads a prompt from a markdown file in the app/prompts directory."""
    filename = f"{name}.md" if not name.endswith(".md") else name
    filepath = os.path.join(PROMPTS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read().strip()
