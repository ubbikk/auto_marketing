"""Carousel service — text → insights → branded slides."""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import anthropic

from .extractor import extract_carousel_content
from .renderer import build_html, build_printable_html

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "carousels"


@dataclass
class CarouselGenerationResult:
    """Result from carousel generation including HTML and usage data."""

    html: str
    carousel_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = "claude-sonnet-4-20250514"


async def generate_carousel_html(
    text: str,
    client: Optional[anthropic.Anthropic] = None,
    message: str = "",
    logo_data_url: Optional[str] = None,
    footer_domain: str = "afta.systems",
) -> CarouselGenerationResult:
    """Generate carousel HTML without PDF rendering.

    Args:
        text: Source text to extract insights from.
        client: Optional Anthropic client.
        message: Optional key message to guide content direction.
        logo_data_url: Optional base64 data URL for target website logo.
        footer_domain: Domain to display in carousel footer.

    Returns:
        CarouselGenerationResult with HTML, carousel_id, and usage data.
    """
    # Step 1: Extract structured content from text via Claude
    extraction_result = await extract_carousel_content(
        text, client=client, message=message
    )

    # Step 2: Build HTML from the template
    html_doc = build_html(
        extraction_result.content,
        logo_data_url=logo_data_url,
        footer_domain=footer_domain,
    )

    # Generate a unique ID for this carousel
    carousel_id = hashlib.md5(html_doc.encode()).hexdigest()[:12]

    # Save HTML for later download
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = _OUTPUT_DIR / f"{carousel_id}.html"
    html_path.write_text(html_doc, encoding="utf-8")

    return CarouselGenerationResult(
        html=html_doc,
        carousel_id=carousel_id,
        input_tokens=extraction_result.input_tokens,
        output_tokens=extraction_result.output_tokens,
        model=extraction_result.model,
    )


def get_printable_html(carousel_id: str) -> Optional[str]:
    """Get print-ready HTML for a previously generated carousel.

    Args:
        carousel_id: The carousel ID returned from generate_carousel_html.

    Returns:
        Print-ready HTML string, or None if not found.
    """
    html_path = _OUTPUT_DIR / f"{carousel_id}.html"
    if not html_path.exists():
        return None

    html_content = html_path.read_text(encoding="utf-8")
    return build_printable_html(html_content)
