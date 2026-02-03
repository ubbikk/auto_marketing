"""Carousel service — text → insights → branded slides → PDF."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import anthropic

from .extractor import extract_carousel_content
from .models import CarouselContent
from .renderer import build_html, render_pdf

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "carousels"


async def generate_carousel(
    text: str,
    output_dir: Optional[Path] = None,
    filename: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
    message: str = "",
    logo_data_url: Optional[str] = None,
    footer_domain: str = "afta.systems",
) -> Path:
    """Full pipeline: text → Claude extraction → HTML → PDF.

    Args:
        text: Source text to extract insights from.
        output_dir: Where to save the PDF. Defaults to data/carousels/.
        filename: PDF filename (without extension). Defaults to timestamp.
        client: Optional Anthropic client.
        message: Optional key message to guide content direction.
        logo_data_url: Optional base64 data URL for target website logo.
        footer_domain: Domain to display in carousel footer.

    Returns:
        Path to the generated PDF file.
    """
    out = output_dir or _OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    name = filename or f"carousel_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_path = out / f"{name}.pdf"

    # Step 1: Extract structured content from text via Claude
    content: CarouselContent = await extract_carousel_content(
        text, client=client, message=message
    )

    # Step 2: Build HTML from the template
    html_doc = build_html(
        content,
        logo_data_url=logo_data_url,
        footer_domain=footer_domain,
    )

    # Step 3: Render to PDF via Playwright
    await render_pdf(html_doc, pdf_path)

    return pdf_path


def run(
    text: str,
    output_dir: Optional[Path] = None,
    filename: Optional[str] = None,
) -> Path:
    """Synchronous wrapper for generate_carousel."""
    return asyncio.run(generate_carousel(text, output_dir, filename))


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.carousel.service <path_to_text_file> [output_filename]")
        sys.exit(1)

    text_path = Path(sys.argv[1])
    if not text_path.exists():
        print(f"File not found: {text_path}")
        sys.exit(1)

    source_text = text_path.read_text(encoding="utf-8")
    out_name = sys.argv[2] if len(sys.argv) > 2 else None
    pdf = run(source_text, filename=out_name)
    print(f"Carousel PDF saved to: {pdf}")
