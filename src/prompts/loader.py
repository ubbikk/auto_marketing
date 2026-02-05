"""Prompt template loader.

Loads prompt templates from the prompts/ directory and renders
them with provided variables using string.Template ($var syntax).

JSON braces in templates are preserved as-is — only $variable
placeholders are substituted.
"""

from functools import lru_cache
from pathlib import Path
from string import Template

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


@lru_cache(maxsize=32)
def _load_raw(name: str) -> str:
    """Load raw template text from file. Cached for performance."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text()


@lru_cache(maxsize=1)
def _load_philosophy() -> str:
    """Load the shared philosophy preamble. Cached — loaded once."""
    path = _PROMPTS_DIR / "philosophy.txt"
    if not path.exists():
        return ""
    return path.read_text()


def render(name: str, **kwargs: str) -> str:
    """Load a prompt template and render it with the given variables.

    Auto-injects $system_philosophy from philosophy.txt if the template
    uses it and the caller didn't provide an explicit value.

    Args:
        name: Template filename without extension (e.g. "generator")
        **kwargs: Template variables to substitute

    Returns:
        Rendered prompt string

    Raises:
        FileNotFoundError: If template file doesn't exist
        KeyError: If a required placeholder has no value provided
    """
    template_text = _load_raw(name)

    # Auto-inject philosophy if template uses it and caller didn't provide it
    if "$system_philosophy" in template_text and "system_philosophy" not in kwargs:
        kwargs["system_philosophy"] = _load_philosophy()

    template = Template(template_text)
    return template.substitute(**kwargs)
