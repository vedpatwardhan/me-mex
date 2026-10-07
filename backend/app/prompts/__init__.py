import os
import re
from functools import lru_cache

PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))


@lru_cache(maxsize=32)
def _read_raw_prompt(name: str) -> str:
    """Reads raw prompt template file and strips developer HTML comments."""
    filename = f"{name}.md" if not name.endswith(".md") else name
    filepath = os.path.join(PROMPTS_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    # Strip HTML comments <!-- ... -->
    content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    return content.strip()


def load_prompt(name: str, **kwargs) -> str:
    """
    Loads prompt template and renders Jinja2-style {{ variable }} placeholders.
    Single curly braces ({ ... }) used in JSON schemas are completely preserved.
    """
    content = _read_raw_prompt(name)
    if kwargs:
        for k, v in kwargs.items():
            pattern = r"\{\{\s*" + re.escape(k) + r"\s*\}\}"
            content = re.sub(pattern, str(v), content)
    return content
