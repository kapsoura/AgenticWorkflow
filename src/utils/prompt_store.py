from functools import lru_cache
from pathlib import Path
from string import Template


_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "configs" / "prompts"


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def render_prompt(name: str, **values) -> str:
    return Template(load_prompt(name)).substitute(**values)