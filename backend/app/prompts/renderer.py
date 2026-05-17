"""Prompt template loading and variable substitution."""

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def render(template_name: str, **kwargs: str) -> str:
    """Load a template file and replace {variables} with kwargs."""
    path = _PROMPT_DIR / f"{template_name}.md"
    template = path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))
    return template
