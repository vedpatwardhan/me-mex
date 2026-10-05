import os
import re
from functools import lru_cache

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Loads a prompt from a markdown file in the app/prompts directory, stripping metadata comments."""
    filename = f"{name}.md" if not name.endswith(".md") else name
    filepath = os.path.join(PROMPTS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Strip HTML comments <!-- ... --> so developer metadata is never sent to the LLM
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return content.strip()
